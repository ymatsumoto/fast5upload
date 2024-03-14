fast5upload
======
`fast5upload` is a tool that works with MinKNOW to automatically upload
your sequenced raw data to our server for further data analyses, basecalling
included.

## Installation

### Prerequisite
We assume that you have finished following the MinKNOW manual to install it onto an
Ubuntu 22.04 machine. You also have an active Internet connection during setup, as well
as during actual run.

### Download the package

You may obtain the latest version of the package from the following URL:
* https://mlstverse.org/release/fast5upload_latest.deb

### Install the package

We recommend using `apt` to complete the installation, so that the libraries this
program depends on could be installed automatically as well.

```bash
sudo apt install ~/Downloads/fast5upload_latest.deb
```

### Basic configurations

Before you can use this tool, you would need to tell it your login information.

```bash
sudo gedit /etc/mlstverse/fast5upload.conf
```

With the opened editor window, please fill in the blanks of "user" and "password".
Save the file, and test your setup.

```bash
sudo fast5upload-debug
```

This program would output a few information regarding your current setup. If you
see your account name being Welcomed, and `You are good to go` at the end,
your configuration is working.

If anything went wrong during such test, please contact us with a copy of the
output for further help.

### Enable fast5upload service

This tool is managed by `systemd`. To use it only for certain runs, execute
the following command before and after the run:

```bash
systemctl start fast5upload

# Run your sequencer

systemctl stop fast5upload
```

If you do not want to start and stop it every time you have a new run, and
just want to upload everything you have to us for analyses, you may instead
enable this service and forget about it till next update. Use the following
command to enable the service:

```bash
systemctl enable --now fast5upload
```

