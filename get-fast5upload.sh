#! /bin/bash

# fast5upload setup script for mlstverse repo
# adapted from get-oma.sh from AOSC

CERT_FILE=mlst-repo-2025-04-ed25519-86620FBF8B1B988EE4125810EE05C034F510E665.gpg

_install_keyring() {
	# Install repository GPG key.
	curl -sSf "https://mlstverse.org/repo/${CERT_FILE}" -o "/etc/apt/trusted.gpg.d/${CERT_FILE}"

	if [ "$?" != '0' ]; then
		echo '
>>> Failed to install the repository keyring!
'
		exit 1
	fi
}

_write_sources_list() {
	# Common routine
	cat > /etc/apt/sources.list.d/mlstverse.list << EOF
deb https://mlstverse.org/repo stable main
EOF

	if [ "$?" != '0' ]; then
		echo '
>>> Failed to set up the repository for mlstverse!
'
                exit 1
        fi

}

_refresh_apt() {
	apt update

	if [ "$?" != '0' ]; then
		echo '
>>> Failed to refresh repository metadata!
'
                exit 1
        fi
}

_install_oma() {
	apt install fast5upload --yes

	if [ "$?" != '0' ]; then
		echo '
>>> Failed to install fast5upload!
'
                exit 1
        fi
}

echo '
=======================================

         Setup for fast5upload

=======================================
'

echo '
Installing mlstverse repository keyring ...
'
_install_keyring

echo '
Configuring mlstverse repository ...
'
_write_sources_list

echo '
Refreshing repository metadata ...
'
_refresh_apt

echo '
Installing fast5upload ...
'
_install_oma
