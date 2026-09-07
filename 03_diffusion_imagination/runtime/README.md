# StreamDiffusion runtime

This directory contains the isolated real-time diffusion service used by the
Morphogenesis diffusion exhibition page. Third-party source code is kept in
`StreamDiffusion/`; local worker and launch files live beside it.

The service uses port `8091`. The main Morphogenesis Agent remains on port
`8080`, so their Python dependencies and network endpoints do not collide.
In exhibition operation, start only the main Agent; it starts, monitors, and
stops this worker automatically. Use the standalone worker launcher only for
diagnostics.
