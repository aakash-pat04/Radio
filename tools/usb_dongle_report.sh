#!/usr/bin/env bash
# Identify USB dongles and check for a usable Bluetooth adapter.
# Plug in ONE dongle at a time, wait ~5 s, then run:
#   tools/usb_dongle_report.sh
# A Bluetooth adapter shows an interface with class=e0 sub=01 proto=01,
# an hciN entry under /sys/class/bluetooth, and a Controller in bluetoothctl.
set -u

echo "== lsusb =="
lsusb

echo
echo "== USB devices and interfaces =="
for dev in /sys/bus/usb/devices/*; do
  [ -f "$dev/idVendor" ] || continue
  vid=$(cat "$dev/idVendor"); pid=$(cat "$dev/idProduct")
  [ "$vid" = "1d6b" ] && continue  # Linux root hubs
  mfr=$(cat "$dev/manufacturer" 2>/dev/null || echo "?")
  prod=$(cat "$dev/product" 2>/dev/null || echo "?")
  echo "$(basename "$dev")  $vid:$pid  $mfr / $prod  (device class $(cat "$dev/bDeviceClass"))"
  for intf in "$dev"/*:*; do
    [ -f "$intf/bInterfaceClass" ] || continue
    cls=$(cat "$intf/bInterfaceClass"); sub=$(cat "$intf/bInterfaceSubClass")
    proto=$(cat "$intf/bInterfaceProtocol")
    driver="(no driver)"
    [ -e "$intf/driver" ] && driver=$(basename "$(readlink "$intf/driver")")
    note=""
    [ "$cls/$sub/$proto" = "e0/01/01" ] && note="  <-- Bluetooth HCI interface"
    [ "$cls" = "03" ] && note="  <-- HID (keyboard/mouse receiver)"
    echo "    if $(basename "$intf")  class=$cls sub=$sub proto=$proto  driver=$driver$note"
  done
done

echo
echo "== Network interfaces (Wi-Fi dongles appear as wlanN) =="
ls /sys/class/net

echo
echo "== Bluetooth controllers known to the kernel =="
if ls /sys/class/bluetooth/hci* >/dev/null 2>&1; then ls /sys/class/bluetooth; else echo "none"; fi

echo
echo "== bluetoothctl =="
if command -v bluetoothctl >/dev/null; then
  timeout 5 bluetoothctl list || true
else
  echo "bluez not installed (sudo apt install -y bluez) - only needed if an HCI interface was found"
fi

echo
echo "== Last kernel messages =="
(sudo -n dmesg 2>/dev/null || dmesg 2>/dev/null) | tail -n 20 || echo "(dmesg needs sudo)"
