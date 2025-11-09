#!/data/data/com.termux/files/usr/bin/bash
wing="full"
NM="kali"
# Download and configure vnc
wget -qO "$DIR/bin/vnc" "https://raw.githubusercontent.com/xiv3r/Kali-Linux-Termux/refs/heads/main/kali_nethunter/vnc" >/dev/null 2>&1 
chmod 755 "$DIR/bin/vnc"

# Add neofetch
wget -qO "$DIR/bin/neofetch" "https://raw.githubusercontent.com/xiv3r/Kali-Linux-Termux/refs/heads/main/kali_nethunter/neofetch" >/dev/null 2>&1
chmod 755 "$DIR/bin/neofetch"

# Add VNC autostart for full installation
if [ "$wimg" = "full" ]; then
    echo "( kali vnc & )" >> "$PREFIX/etc/bash.bashrc"
fi

# Add uninstallation config file
cat > "$PREFIX/bin/$NM-uninstall" << EOF
#!/data/data/com.termux/files/usr/bin/bash

rm -rf "$HOME/$DIR"
rm -f "$PREFIX/bin/$NM"
sed -i '/termux-wake-lock/d' "$PREFIX/etc/bash.bashrc"
sed -i '/clear/d' "$PREFIX/etc/bash.bashrc"
sed -i '/$NM -r/d' "$PREFIX/etc/bash.bashrc"
sed -i '/( kali vnc & )/d' "$PREFIX/etc/bash.bashrc"
rm -f "$PREFIX/bin/$NM-uninstall"
EOF
chmod 755 "$PREFIX/bin/$NM-uninstall"

# Modify .bash_profile
sed -i '/if/,/fi/d' "$DIR/root/.bash_profile"

# Set SUID for sudo and su
chmod +s "$DIR/usr/bin/sudo"
chmod +s "$DIR/usr/bin/su"

# Fix DNS resolver
cat > "$DIR/etc/resolv.conf" << EOF
nameserver 9.9.9.9
nameserver 8.8.8.8
nameserver 1.1.1.1
EOF

# Fix sudoer file
cat > "$DIR/etc/sudoers.d/$NM" << EOF
$NM    ALL=(ALL:ALL) ALL
EOF

# Neofetch
sed -i '/neofetch/d' "$DIR/etc/bash.bashrc"
cat >> "$DIR/etc/bash.bashrc" << EOF
neofetch
EOF

# Configure sudo.conf
cat > "$DIR/etc/sudo.conf" << EOF
Set disable_coredump false
EOF

# Modify user and group IDs
USRID=$(id -u)
GRPID=$(id -g)
"$NM" -r usermod -u "$USRID" "$NM" >/dev/null 2>&1
"$NM" -r groupmod -g "$GRPID" "$NM" >/dev/null 2>&1

# Delete Tarball
rm -f "$IMAGE_NAME"
rm -f install.sh

# Display success message
cat << EOF

[*] To Login Kali Nethunter Type: $NM
EOF
