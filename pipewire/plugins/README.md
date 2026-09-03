# librnnoise_ladspa.so

Neural noise suppression plugin used by `98-drivethru-rnnoise.conf` to clean
wind/engine/road noise off the outdoor mic continuously, including while
someone is talking (the Silero VAD gate in `server/voice_detector.py` only
mutes between utterances - it doesn't touch the signal during speech).

Built from https://github.com/werman/noise-suppression-for-voice (RNNoise
wrapped as a LADSPA plugin). Not packaged for Ubuntu 22.04, so it's built
from source and referenced here by absolute path instead of installed
system-wide.

## Rebuilding

```bash
sudo apt-get install -y build-essential cmake
git clone --recursive https://github.com/werman/noise-suppression-for-voice.git
cd noise-suppression-for-voice
mkdir build && cd build
cmake -DBUILD_TESTS=OFF -DBUILD_VST_PLUGIN=OFF -DBUILD_VST3_PLUGIN=OFF \
      -DBUILD_LV2_PLUGIN=OFF -DBUILD_AU_PLUGIN=OFF -DBUILD_AUV3_PLUGIN=OFF \
      -DBUILD_LADSPA_PLUGIN=ON ..
make -j$(nproc)
cp bin/ladspa/librnnoise_ladspa.so /home/steve/drivesystem/pipewire/plugins/
```

Then restart PipeWire: `systemctl --user restart pipewire pipewire-pulse wireplumber`

## Note on the plugin path

PipeWire's own example config (`/usr/share/pipewire/filter-chain/source-rnnoise.conf`)
says the `.so` suffix gets appended automatically - that wasn't true for an
absolute path on this PipeWire version (1.0.7). Include `.so` explicitly in
`plugin = "..."` or it fails with "No such file or directory" even though
the file exists.
