# Demo Recording Guide

## How to Record the Demo GIF

1. Start the full stack: `docker-compose up -d`
2. Open `http://localhost:3000` in your browser
3. Use a screen recorder (OBS, Loom, or `peek` on Linux) to capture:
   - Type a topic in the Studio input (e.g., "赛博朋克火星殖民，60秒，冷色调")
   - Click "开始创作" and watch the real-time WebSocket progress
   - Review and approve the generated storyboard scenes
   - Watch the parallel generation progress (image + TTS + video)
   - See the final assembled video in the output panel
4. Export as `demo.gif` (recommended: 1280×720, 15fps, max 10MB)
5. Place the file at `docs/demo.gif`
6. Update `README.md` and `README-CN.md` to reference: `![Demo](docs/demo.gif)`

## Recommended Tools

- **macOS**: Gifox, Kap, or QuickTime + ffmpeg conversion
- **Linux**: Peek, Byzanz, or OBS + ffmpeg conversion  
- **Windows**: ScreenToGif, ShareX

## FFmpeg GIF Conversion

```bash
# Convert MP4 to optimized GIF
ffmpeg -i demo.mp4 -vf "fps=12,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
  -loop 0 docs/demo.gif
```
