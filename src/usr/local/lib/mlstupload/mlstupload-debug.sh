#! /bin/bash

echo Checking versions of installed packages...
VERSION_BAD=0

dpkg --list ont-python | grep ii || VERSION_BAD=1

if [ $(uname -m) == "x86_64" ]
then dpkg --list ont-standalone-minknow-release | grep ii || VERSION_BAD=1
fi

dpkg --list fast5upload | grep ii || VERSION_BAD=1
if [ $VERSION_BAD -eq 1 ]
	then echo MinKNOW and fast5upload installation incomplete.
	echo Please follow MinKNOW installation instruction to install MinKNOW,
	echo then follow our instruction to install fast5upload.
	exit 1
fi
if [ $(dpkg --list ont-python | grep ii | awk '{print $3}' | cut -d "." -f 1) -eq 3 ]
	then echo Python Version OK
	else echo MinKNOW bundled unsupported version of Python.
	echo Please use apt update \&\& apt upgrade to upgrade to the latest version.
	exit 1
fi

if [ $(uname -m) == "x86_64" ]
then if [ $(dpkg --list ont-standalone-minknow-release | grep ii | awk '{print $3}' | cut -d "." -f 1) -ge 22 ]
	then echo MinKNOW Version OK
	else echo MinKNOW is too old.
		echo please use apt update \&\& apt upgrade to upgrade to the latest version.
		exit 1
	fi
fi
echo MinKNOW and fast5upload version OK.

echo Checking dependencies...
/opt/ont/minknow/ont-python/bin/python -m pip show watchdog | grep Version || VERSION_BAD=1
if [ $VERSION_BAD -eq 1 ]
	then echo Watchdog installation failed.
	echo Please reinstall fast5upload.
	exit 1
fi
if [ $(/opt/ont/minknow/ont-python/bin/python -m pip show watchdog | grep Location | cut -d " " -f 2 | cut -d "/" -f 1-6) != "/opt/ont/minknow/ont-python/lib" ]
	then echo Watchdog installed to wrong location.
	/opt/ont/minknow/ont-python/bin/python -m pip show watchdog | grep Location |cut -d " " -f 2 | cut -d "/" -f 1-6
	echo Please contact support to install watchdog to correct location.
	exit 1
fi
echo Dependencies checked OK

/opt/ont/minknow/ont-python/bin/python "$(dirname $0)/mlstupload-debug.py"
