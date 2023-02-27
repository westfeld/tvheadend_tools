# tvheadend_tools
A small collection of useful scripts to use in combination with the [tvheadend software](https://tvheadend.org/).

## Transcode_recordings
Post-processing script that transcodes an MPEG2 transport stream to h264 mp4 file with embedded metadata
from the tvheadend EPG. Additionally it uses comskip to detect commercials in the recording. The position of the commercials
is then added as chapters to the mp4 file.

### Prerequisites
This script uses python3, requests, ffmpeg and comskip. On RaspberryPi OS it can be installed with `apt install python3 python3-requests ffmpeg comskip`.

The ffmpeg transcoding command uses the hardware acceleration
of the RaspberryPi 4B to achieve faster encoding. A decomb filter is also used for SD content. The video bitrate of the transcoded
file is given by a compression factor relative to the source video rate. For a transcoding from an MPEG-2 video stream to a h264 file
a compression factor of 0.6 is a good starting point.


### Usage

Configure the script by modifying the global variables `TVHEADEND_SERVER_URL` to point to
the url of the server and for authentication username and password in `TVHEADEND_SERVER_USER`
and `TVHEADEND_SERVER_PASSWD`, respectively. Optionally, a config file for comskip can be
passed to the script.

Use the script as a post-processing script in a tvheadend DVR configuration.
Invoke the script like `transcode_recordings.py %U %e [path to ini file for comskip]`.
