Pullover CLI
=========

What's this
-----

Using Pushover Open Client API to pull pushover notifications realtime, and show it using libnotify.

Status
-----

- Still alpha
- Device Register not implemented yet (Related API is undocumented)

Usage
-----

- Login to pushover web client
- Open browser console, prints `Pushover.userSecret` and `Pushover.deviceId`
- `pip install -r requirements.txt`, install `python-gobject`
- `python pullover-cli.py <SECRET> <DEVICEID>`
