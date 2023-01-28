# tvheadend_tools
A small collection of useful scripts to use in combination with the tvheadend software

## Transcode_recordings
Post-processing script that transcodes an MPEG2 transport stream to h264 with embedded metadata
from the tvheadend EPG.

### Prerequisites
This script uses python3, requests and ffmpeg

### Usage

Use the script as a post-processing script in a tvheadend DVR configuration.
Invoke the script like `transcode_recordings.py %U %e`.
