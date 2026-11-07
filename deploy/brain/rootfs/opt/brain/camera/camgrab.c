/* camgrab: capture from the sunxi-vin camera (Radxa Camera 8M 219 / IMX219)
 * with the Allwinner ISP running (auto exposure / white balance).
 *
 *   camgrab [width height frames out.nv12 [video_id]]
 *       save one NV12 frame (the last of `frames`) to out.nv12
 *   camgrab --mjpeg width height fps quality [video_id [flip]]
 *       stream JPEG frames to stdout until SIGTERM/SIGINT or stdout closes;
 *       flip 1 turns the picture upside down (sensor h+v flip). While running,
 *       the lines "flip 0" / "flip 1" on stdin change it live;
 *       each frame is a 4-byte big-endian length followed by the JPEG bytes.
 *       JPEG is made by the hardware encoder (Allwinner video engine).
 *
 * Camera tuning: /opt/brain/camera/imx219_tuning.bin (or CAMGRAB_TUNING=path,
 * CAMGRAB_TUNING= for the built-in defaults) replaces the IMX219 ISP settings.
 *
 * Build: gcc -O2 -o camgrab camgrab.c -lAWIspApi -lisp -lisp_ini \
 *            -lvencoder -lMemAdapter -lVE -lcdc_base -lpthread
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <unistd.h>
#include "AWIspApi.h"
#include "sunxi_camera_v2.h"
#include "vencoder.h"
#include "memoryAdapter.h"
#include "sc_interface.h"

#define NBUF 4

/* IMX219 tuning blocks exported by libisp_ini.so. libisp copies them when the
 * ISP starts, so a tuning file can replace them first (see load_tuning). */
extern unsigned char imx219_mipi_isp_test_settings[124];
extern unsigned char imx219_mipi_isp_3a_settings[2724];
extern unsigned char imx219_mipi_isp_tuning_settings[99440];
extern unsigned char imx219_mipi_isp_iso_settings[13996];
#define TUNING_FILE_DEFAULT "/opt/brain/camera/imx219_tuning.bin"
#define TUNING_HEADER 74          /* u32 size, 20 B name, 50 B note (isp_param_config.bin layout) */
#define SENSOR_FPS 30

static volatile sig_atomic_t stop_flag;
static volatile int want_flip = -1;     /* set by the stdin thread, applied by the main loop */
static void on_signal(int sig) { (void)sig; stop_flag = 1; }

static int xioctl(int fd, unsigned long req, void *arg)
{
	int r;
	do r = ioctl(fd, req, arg); while (r < 0 && errno == EINTR && !stop_flag);
	return r;
}

struct cam {
	int fd, width, height, nplanes;
	size_t stride, uv_offset;
	void *mem[NBUF][VIDEO_MAX_PLANES];
	size_t len[NBUF][VIDEO_MAX_PLANES];
	AWIspApi *isp;
	int isp_id;
};

/* Load a camera tuning file (isp_param_config.bin layout: header + test, 3a,
 * tuning and iso blocks) over libisp's built-in IMX219 defaults. Path from
 * CAMGRAB_TUNING (empty = keep the built-in defaults), else the default file
 * if it exists. */
static void load_tuning(void)
{
	const char *path = getenv("CAMGRAB_TUNING");
	if (!path) path = TUNING_FILE_DEFAULT;
	if (!*path) return;
	FILE *f = fopen(path, "rb");
	if (!f) {
		if (getenv("CAMGRAB_TUNING")) fprintf(stderr, "camgrab: tuning %s: %s\n", path, strerror(errno));
		return;
	}
	static unsigned char buf[TUNING_HEADER + 124 + 2724 + 99440 + 13996 + 1];
	size_t n = fread(buf, 1, sizeof buf, f);
	fclose(f);
	unsigned int size = buf[0] | buf[1] << 8 | buf[2] << 16 | (unsigned)buf[3] << 24;
	if (n != sizeof buf - 1 || size != sizeof buf - 1 - TUNING_HEADER) {
		fprintf(stderr, "camgrab: tuning %s has the wrong size, ignored\n", path);
		return;
	}
	unsigned char *p = buf + TUNING_HEADER;
	memcpy(imx219_mipi_isp_test_settings, p, 124); p += 124;
	memcpy(imx219_mipi_isp_3a_settings, p, 2724); p += 2724;
	memcpy(imx219_mipi_isp_tuning_settings, p, 99440); p += 99440;
	memcpy(imx219_mipi_isp_iso_settings, p, 13996);
	fprintf(stderr, "camgrab: tuning %s loaded\n", path);
}

static int cam_open(struct cam *c, int video_id, int width, int height)
{
	char dev[32];
	snprintf(dev, sizeof dev, "/dev/video%d", video_id);
	memset(c, 0, sizeof *c);
	c->isp_id = -1;
	c->fd = open(dev, O_RDWR | O_NONBLOCK);
	if (c->fd < 0) { perror(dev); return -1; }

	int input = 0;
	if (xioctl(c->fd, VIDIOC_S_INPUT, &input) < 0) { perror("S_INPUT"); return -1; }

	struct v4l2_streamparm parm = {0};
	parm.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	parm.parm.capture.timeperframe.numerator = 1;
	parm.parm.capture.timeperframe.denominator = SENSOR_FPS;
	if (xioctl(c->fd, VIDIOC_S_PARM, &parm) < 0) perror("S_PARM (ignored)");

	struct sensor_isp_cfg cfg = {0};
	if (xioctl(c->fd, VIDIOC_SET_SENSOR_ISP_CFG, &cfg) < 0) perror("SET_SENSOR_ISP_CFG (ignored)");

	struct v4l2_format fmt = {0};
	fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	fmt.fmt.pix_mp.width = width;
	fmt.fmt.pix_mp.height = height;
	fmt.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_NV12;
	fmt.fmt.pix_mp.field = V4L2_FIELD_NONE;
	if (xioctl(c->fd, VIDIOC_S_FMT, &fmt) < 0) { perror("S_FMT"); return -1; }
	if (xioctl(c->fd, VIDIOC_G_FMT, &fmt) < 0) { perror("G_FMT"); return -1; }
	c->width = fmt.fmt.pix_mp.width;
	c->height = fmt.fmt.pix_mp.height;
	c->nplanes = fmt.fmt.pix_mp.num_planes;
	/* sunxi-vin one-plane NV12: rows of exactly `width` bytes; the UV plane
	 * starts after the Y rows rounded up to 16 (1080 -> 1088). The driver's
	 * bytesperline is width*1.5, not a row stride, so it is not used. */
	c->stride = c->width;
	c->uv_offset = (size_t)c->width * ((c->height + 15) & ~15);
	fprintf(stderr, "camgrab: %dx%d, %d plane(s), stride %zu, uv offset %zu\n",
		c->width, c->height, c->nplanes, c->stride, c->uv_offset);

	struct v4l2_requestbuffers req = {0};
	req.count = NBUF;
	req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	req.memory = V4L2_MEMORY_MMAP;
	if (xioctl(c->fd, VIDIOC_REQBUFS, &req) < 0 || req.count < 2) { perror("REQBUFS"); return -1; }

	for (unsigned i = 0; i < req.count && i < NBUF; i++) {
		struct v4l2_plane planes[VIDEO_MAX_PLANES] = {0};
		struct v4l2_buffer buf = {0};
		buf.type = req.type; buf.memory = V4L2_MEMORY_MMAP; buf.index = i;
		buf.length = c->nplanes; buf.m.planes = planes;
		if (xioctl(c->fd, VIDIOC_QUERYBUF, &buf) < 0) { perror("QUERYBUF"); return -1; }
		for (int p = 0; p < c->nplanes; p++) {
			c->len[i][p] = planes[p].length;
			if (p == 0 && c->nplanes == 1 && c->uv_offset + c->stride * c->height / 2 > planes[p].length) {
				fprintf(stderr, "camgrab: buffer %u bytes too small for %dx%d NV12\n",
					planes[p].length, c->width, c->height);
				return -1;
			}
			c->mem[i][p] = mmap(NULL, planes[p].length, PROT_READ | PROT_WRITE, MAP_SHARED,
					    c->fd, planes[p].m.mem_offset);
			if (c->mem[i][p] == MAP_FAILED) { perror("mmap"); return -1; }
		}
		if (xioctl(c->fd, VIDIOC_QBUF, &buf) < 0) { perror("QBUF"); return -1; }
	}

	enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	if (xioctl(c->fd, VIDIOC_STREAMON, &type) < 0) { perror("STREAMON"); return -1; }

	load_tuning();
	c->isp = CreateAWIspApi();
	if (c->isp) {
		c->isp->ispApiInit();
		c->isp_id = c->isp->ispGetIspId(video_id);
		if (c->isp_id < 0 || c->isp->ispStart(c->isp_id) != 0) {
			fprintf(stderr, "camgrab: isp start failed (id %d)\n", c->isp_id);
			c->isp_id = -1;
		}
	}
	return 0;
}

static void cam_close(struct cam *c)
{
	if (c->isp && c->isp_id >= 0) {
		c->isp->ispStop(c->isp_id);
		c->isp->ispWaitToExit(c->isp_id);
	}
	if (c->isp) { c->isp->ispApiUnInit(); DestroyAWIspApi(c->isp); }
	if (c->fd >= 0) {
		enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
		ioctl(c->fd, VIDIOC_STREAMOFF, &type);
		close(c->fd);
	}
}

/* Wait for a frame; returns the buffer index, or -1 on timeout/stop/error. */
static int cam_dequeue(struct cam *c, struct v4l2_buffer *buf, struct v4l2_plane *planes)
{
	while (!stop_flag) {
		fd_set fds; FD_ZERO(&fds); FD_SET(c->fd, &fds);
		struct timeval tv = {2, 0};
		int r = select(c->fd + 1, &fds, NULL, NULL, &tv);
		if (r < 0 && errno == EINTR) continue;
		if (r <= 0) { fprintf(stderr, "camgrab: frame timeout\n"); return -1; }
		memset(buf, 0, sizeof *buf);
		memset(planes, 0, sizeof(struct v4l2_plane) * VIDEO_MAX_PLANES);
		buf->type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE; buf->memory = V4L2_MEMORY_MMAP;
		buf->length = c->nplanes; buf->m.planes = planes;
		if (xioctl(c->fd, VIDIOC_DQBUF, buf) < 0) {
			if (errno == EAGAIN) continue;
			perror("DQBUF"); return -1;
		}
		return buf->index;
	}
	return -1;
}

/* Upside down = sensor horizontal + vertical flip (a 180 degree turn). */
static int cam_set_flip(struct cam *c, int on)
{
	struct v4l2_control h = {V4L2_CID_HFLIP, on ? 1 : 0}, v = {V4L2_CID_VFLIP, on ? 1 : 0};
	if (xioctl(c->fd, VIDIOC_S_CTRL, &h) < 0 || xioctl(c->fd, VIDIOC_S_CTRL, &v) < 0) {
		fprintf(stderr, "camgrab: flip %d failed: %s\n", on, strerror(errno));
		return -1;
	}
	fprintf(stderr, "camgrab: flip %d\n", on);
	return 0;
}

static void *stdin_commands(void *arg)
{
	(void)arg;
	char line[64];
	while (fgets(line, sizeof line, stdin)) {
		if (strncmp(line, "flip ", 5) == 0)
			want_flip = atoi(line + 5) ? 1 : 0;
	}
	return NULL;
}

static int write_all(int fd, const void *data, size_t n)
{
	const unsigned char *p = data;
	while (n) {
		ssize_t w = write(fd, p, n);
		if (w < 0 && errno == EINTR && !stop_flag) continue;
		if (w <= 0) return -1;
		p += w; n -= (size_t)w;
	}
	return 0;
}

/* Hardware JPEG encoder (Allwinner video engine through libvencoder). */
struct hwjpeg {
	struct ScMemOpsS *mem;
	VideoEncoder *enc;
	int width, height;
};

static void hwjpeg_close(struct hwjpeg *j)
{
	if (j->enc) {
		ReleaseAllocInputBuffer(j->enc);
		VideoEncUnInit(j->enc);
		VideoEncDestroy(j->enc);
	}
	if (j->mem) CdcMemClose(j->mem);
	memset(j, 0, sizeof *j);
}

static int hwjpeg_open(struct hwjpeg *j, int width, int height, int quality)
{
	memset(j, 0, sizeof *j);
	j->width = width; j->height = height;
	j->mem = MemAdapterGetOpsS();
	if (!j->mem || CdcMemOpen(j->mem) < 0) { fprintf(stderr, "camgrab: memory adapter failed\n"); j->mem = NULL; return -1; }
	j->enc = VideoEncCreate(VENC_CODEC_JPEG);
	if (!j->enc) { fprintf(stderr, "camgrab: VideoEncCreate failed\n"); hwjpeg_close(j); return -1; }
	int mode = 0;                        /* plain JPEG per frame */
	VideoEncSetParameter(j->enc, VENC_IndexParamJpegQuality, &quality);
	VideoEncSetParameter(j->enc, VENC_IndexParamJpegEncMode, &mode);
	VencBaseConfig base;
	memset(&base, 0, sizeof base);
	base.nInputWidth = width; base.nInputHeight = height;
	base.nDstWidth = width; base.nDstHeight = height;
	base.nStride = width;
	base.eInputFormat = VENC_PIXEL_YUV420SP;  /* NV12 */
	base.memops = j->mem;
	if (VideoEncInit(j->enc, &base) != 0) { fprintf(stderr, "camgrab: VideoEncInit failed\n"); hwjpeg_close(j); return -1; }
	VencAllocateBufferParam bp = {2, (unsigned)(width * height), (unsigned)(width * height / 2)};
	if (AllocInputBuffer(j->enc, &bp) != 0) { fprintf(stderr, "camgrab: AllocInputBuffer failed\n"); hwjpeg_close(j); return -1; }
	return 0;
}

/* Encode one NV12 camera frame; calls emit() with the JPEG bytes. */
static int hwjpeg_encode(struct hwjpeg *j, const struct cam *c, const unsigned char *nv12,
			 int (*emit)(const unsigned char *, size_t, const unsigned char *, size_t))
{
	VencInputBuffer in;
	memset(&in, 0, sizeof in);
	if (GetOneAllocInputBuffer(j->enc, &in) != 0) return -1;
	for (int y = 0; y < c->height; y++)
		memcpy(in.pAddrVirY + (size_t)y * c->width, nv12 + (size_t)y * c->stride, c->width);
	for (int y = 0; y < c->height / 2; y++)
		memcpy(in.pAddrVirC + (size_t)y * c->width, nv12 + c->uv_offset + (size_t)y * c->stride, c->width);
	FlushCacheAllocInputBuffer(j->enc, &in);
	AddOneInputBuffer(j->enc, &in);
	int r = VideoEncodeOneFrame(j->enc);
	AlreadyUsedInputBuffer(j->enc, &in);
	ReturnOneAllocInputBuffer(j->enc, &in);
	if (r != 0) { fprintf(stderr, "camgrab: VideoEncodeOneFrame failed (%d)\n", r); return -1; }
	VencOutputBuffer out;
	memset(&out, 0, sizeof out);
	if (GetOneBitstreamFrame(j->enc, &out) != 0) return -1;
	int bad = emit(out.pData0, out.nSize0, out.pData1, out.nSize1);
	FreeOneBitStreamFrame(j->enc, &out);
	return bad;
}

/* Frames go to a private copy of stdout; fd 1 itself is pointed at stderr so
 * banners and logs printed by the ISP and encoder libraries can't corrupt them. */
static int frame_fd = 1;

static int emit_frame(const unsigned char *a, size_t na, const unsigned char *b, size_t nb)
{
	size_t n = na + nb;
	unsigned char hdr[4] = {n >> 24, n >> 16, n >> 8, n};
	return write_all(frame_fd, hdr, 4) || write_all(frame_fd, a, na) || (nb && write_all(frame_fd, b, nb));
}

static int run_mjpeg(int argc, char **argv)
{
	if (argc < 6) {
		fprintf(stderr, "usage: camgrab --mjpeg width height fps quality [video_id]\n");
		return 2;
	}
	int width = atoi(argv[2]), height = atoi(argv[3]);
	double fps = atof(argv[4]);
	int quality = atoi(argv[5]);
	int video_id = argc > 6 ? atoi(argv[6]) : 0;
	int flip = argc > 7 ? atoi(argv[7]) != 0 : 0;
	if (width < 64 || height < 64 || width % 16 || height % 16 || fps <= 0 || fps > SENSOR_FPS ||
	    quality < 10 || quality > 95) {
		fprintf(stderr, "camgrab: width/height must be multiples of 16, fps 1..30, quality 10..95\n");
		return 2;
	}
	fflush(stdout);
	frame_fd = dup(1);
	if (frame_fd < 0 || dup2(2, 1) < 0) { perror("dup"); return 1; }

	struct cam c;
	if (cam_open(&c, video_id, width, height) < 0) { cam_close(&c); return 1; }
	if (c.nplanes != 1) { fprintf(stderr, "camgrab: expected one-plane NV12\n"); cam_close(&c); return 1; }
	struct hwjpeg j;
	if (hwjpeg_open(&j, c.width, c.height, quality) < 0) { cam_close(&c); return 1; }
	if (flip) cam_set_flip(&c, 1);
	int applied_flip = flip;
	/* the command thread must not take SIGTERM/SIGINT: they have to reach this loop */
	sigset_t block, old;
	sigemptyset(&block); sigaddset(&block, SIGTERM); sigaddset(&block, SIGINT);
	pthread_sigmask(SIG_BLOCK, &block, &old);
	pthread_t cmd_thread;
	if (pthread_create(&cmd_thread, NULL, stdin_commands, NULL) == 0)
		pthread_detach(cmd_thread);
	pthread_sigmask(SIG_SETMASK, &old, NULL);
	int rc = 0;
	/* keep `fps` of every SENSOR_FPS frames; skip the first second while exposure settles */
	double acc = 0;
	int settle = SENSOR_FPS;
	while (!stop_flag) {
		struct v4l2_plane planes[VIDEO_MAX_PLANES];
		struct v4l2_buffer buf;
		int i = cam_dequeue(&c, &buf, planes);
		if (i < 0) { rc = stop_flag ? 0 : 1; break; }
		int f = want_flip;
		if (f >= 0 && f != applied_flip && cam_set_flip(&c, f) == 0)
			applied_flip = f;
		if (settle > 0) settle--;
		else if ((acc += fps) >= SENSOR_FPS) {
			acc -= SENSOR_FPS;
			int bad = hwjpeg_encode(&j, &c, c.mem[i][0], emit_frame);
			if (bad) { if (!stop_flag) rc = 1; stop_flag = 1; }   /* encoder error or reader gone */
		}
		xioctl(c.fd, VIDIOC_QBUF, &buf);
	}
	hwjpeg_close(&j);
	cam_close(&c);
	return rc;
}

static int run_still(int argc, char **argv)
{
	int width = argc > 2 ? atoi(argv[1]) : 1920;
	int height = argc > 2 ? atoi(argv[2]) : 1080;
	int frames = argc > 3 ? atoi(argv[3]) : 60;
	const char *out = argc > 4 ? argv[4] : "/tmp/cam.nv12";
	int video_id = argc > 5 ? atoi(argv[5]) : 0;
	struct cam c;
	if (cam_open(&c, video_id, width, height) < 0) { cam_close(&c); return 1; }
	int rc = 1;
	for (int n = 0; n < frames && !stop_flag; n++) {
		struct v4l2_plane planes[VIDEO_MAX_PLANES];
		struct v4l2_buffer buf;
		int i = cam_dequeue(&c, &buf, planes);
		if (i < 0) break;
		if (n == frames - 1) {
			FILE *f = fopen(out, "wb");
			if (!f) { perror(out); }
			else {
				/* write packed NV12: Y rows then UV rows, no padding */
				for (int y = 0; y < c.height; y++)
					fwrite((unsigned char *)c.mem[i][0] + (size_t)y * c.stride, 1, c.width, f);
				for (int y = 0; y < c.height / 2; y++)
					fwrite((unsigned char *)c.mem[i][0] + c.uv_offset + (size_t)y * c.stride, 1, c.width, f);
				fclose(f);
				fprintf(stderr, "camgrab: saved frame %d to %s\n", n, out);
				rc = 0;
			}
		}
		xioctl(c.fd, VIDIOC_QBUF, &buf);
	}
	cam_close(&c);
	return rc;
}

int main(int argc, char **argv)
{
	struct sigaction sa = {0};
	sa.sa_handler = on_signal;           /* no SA_RESTART: wake up select/write */
	sigaction(SIGTERM, &sa, NULL);
	sigaction(SIGINT, &sa, NULL);
	signal(SIGPIPE, SIG_IGN);
	if (argc > 1 && strcmp(argv[1], "--mjpeg") == 0)
		return run_mjpeg(argc, argv);
	return run_still(argc, argv);
}
