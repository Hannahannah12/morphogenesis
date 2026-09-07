# Exhibition session outputs

This directory is the single runtime destination for captured crystal sessions.
Raw camera recordings remain in `../input` and are never overwritten.

Each session has one folder:

```text
crystal_N/
  source/
    crystallization.mp4
  01_material_analysis/
    edge.mp4
    threshold.mp4
    spacetime.mp4
    motion.mp4
  02_structural_resonance/
    attention_blob.mp4
    manifest.json
    patches/
  session.json
```

Direction 03 is live StreamDiffusion and therefore has no required output
folder. When a generated trace is intentionally recorded, its optional path is:

```text
crystal_N/03_diffusion_imagination/diffusion_capture.mp4
```

All required videos use H.264 MP4 so the exhibition HTML pages can play them
directly. `session.json` links the retained source and each direction's current
state without duplicating large media.

Exhibition geometry is aspect-aware and uses a common 720px height:

- 16:9 sources remain 1280×720.
- Square sources remain 720×720 and are centred proportionally on landscape
  screens; they are never stretched.
- Structural Resonance keeps two 720×720 panels in one 1440×720 video while
  its DINO attention and patch coordinates are calculated from the complete
  source frame.
