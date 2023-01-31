# tvheadend_tools
A small collection of useful scripts to use in combination with the [tvheadend software](https://tvheadend.org/).

## Transcode_recordings
Post-processing script that transcodes an MPEG2 transport stream to h264 mp4 file with embedded metadata
from the tvheadend EPG.

### Prerequisites
This script uses python3, requests and ffmpeg. On RaspberryPi OS it can be installed with `apt install python3 python3-requests ffmpeg`.

The ffmpeg transcoding command uses the hardware acceleration
of the RaspberryPi 4B to achieve faster encoding. A decomb filter is also used for SD content.


### Usage

Configure the script by modifying the global variables `TVHEADEND_SERVER_URL` to point to
the url of the server and for authentication username and password in `TVHEADEND_SERVER_USER`
and `TVHEADEND_SERVER_PASSWD`, respectively.

Use the script as a post-processing script in a tvheadend DVR configuration.
Invoke the script like `transcode_recordings.py %U %e`.
