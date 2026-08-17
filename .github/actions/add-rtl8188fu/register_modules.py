#!/usr/bin/env python3
"""Register the NetHunter wireless modules with kleaf.

Kleaf fails a kernel_build when an in-tree module is built but not declared
in module_outs/module_implicit_outs ("built but not copied"). The
define_common_kernels target_configs in common/BUILD.bazel only supports
module_implicit_outs, which is sourced either from get_gki_modules_list()
(_COMMON_GKI_MODULES_LIST in modules.bzl) or written inline in BUILD.bazel.
This script merges the modules this action enables (cfg80211, mac80211,
mac80211_hwsim, rtl8188fu and the in-tree NetHunter wireless toolbox) into
whichever form the checked-out kernel uses, keeping the list sorted.

Handled layouts:
  * modules.bzl with _COMMON_GKI_MODULES_LIST (android14-5.15, android14-6.1
    2024-08+ and 2025+, android15-6.6, android16-6.12, android17-6.18) or
    COMMON_GKI_MODULES_LIST without the underscore (android14-6.1 up to
    2024-07): sorted merge. Old branches feed both module_implicit_outs and
    gki_system_dlkm_modules from this variable, so a single list edit covers
    the whole build.
  * BUILD.bazel with inline "module_implicit_outs": [...] lists
    (android13-5.15): sorted merge into every such list.
  * Neither (android12/13-5.10 legacy build.sh): nothing to do.

Idempotent: safe to run repeatedly (skips when the marker is already present).
"""
import os
import re
import sys

ADDS = [
    # NetHunter wireless modules (cfg80211/mac80211/rtl8188fu + in-tree toolbox)
    "drivers/net/usb/cdc_ether.ko",
    "drivers/net/usb/cdc_mbim.ko",
    "drivers/net/usb/rndis_host.ko",
    "drivers/usb/class/cdc-wdm.ko",
    "drivers/net/wireless/ath/ath.ko",
    "drivers/net/wireless/ath/ath9k/ath9k_common.ko",
    "drivers/net/wireless/ath/ath9k/ath9k_htc.ko",
    "drivers/net/wireless/ath/ath9k/ath9k_hw.ko",
    "drivers/net/wireless/mac80211_hwsim.ko",
    "drivers/net/wireless/mediatek/mt7601u/mt7601u.ko",
    "drivers/net/wireless/ralink/rt2x00/rt2800lib.ko",
    "drivers/net/wireless/ralink/rt2x00/rt2800usb.ko",
    "drivers/net/wireless/ralink/rt2x00/rt2x00lib.ko",
    "drivers/net/wireless/ralink/rt2x00/rt2x00usb.ko",
    "drivers/net/wireless/realtek/rtl8xxxu/rtl8xxxu.ko",
    "drivers/net/wireless/realtek/rtl8188fu/rtl8188fu.ko",
    "net/mac80211/mac80211.ko",
    "net/wireless/cfg80211.ko",
]

MARKER = "rtl8188fu.ko"

_MODULE_LIST_RE = re.compile(
    r'(_?COMMON_GKI_MODULES_LIST\s*=\s*\[)(.*?)(\n\])', re.DOTALL
)
_IMPLICIT_OUTS_RE = re.compile(
    r'(module_implicit_outs"\s*:\s*\[)(.*?)(\n\s*\],)', re.DOTALL
)


def _sorted_insert(text: str) -> str:
    """Insert ADDS at sorted positions inside a "[...]" list body.

    Re-emits the whole body so the result stays "keep sorted" regardless of
    whether any anchor was present.
    """
    entries = re.findall(r'\n(\s*)"([^"]+\.ko)",', text)
    existing = {name for _, name in entries}
    merged = sorted(existing | set(ADDS))
    ind = entries[0][0] if entries else "        "
    return "\n" + "\n".join(f'{ind}"{name}",' for name in merged)


def _patch_list(text: str, regex: re.Pattern) -> int:
    """Sorted-merge ADDS into every match of `regex`; returns match count."""
    def _repl(m):
        return m.group(1) + _sorted_insert(m.group(2)) + m.group(3)
    text, n = regex.subn(_repl, text)
    return n, text


def main() -> int:
    target = "."
    if len(sys.argv) == 2:
        target = sys.argv[1]
    elif len(sys.argv) > 2:
        print("usage: register_modules.py [<dir-or-file>]", file=sys.stderr)
        return 1
    p = os.path.abspath(target)
    if os.path.isdir(p):
        candidates = [(os.path.join(p, "modules.bzl"), _MODULE_LIST_RE),
                      (os.path.join(p, "BUILD.bazel"), _IMPLICIT_OUTS_RE)]
    elif os.path.isfile(p):
        candidates = [(p, _MODULE_LIST_RE), (p, _IMPLICIT_OUTS_RE)]
    else:
        print(f"{p}: not found", file=sys.stderr)
        return 1

    for path, regex in candidates:
        if not os.path.isfile(path):
            continue
        s = open(path).read()
        if MARKER in s:
            print(f"{path}: already patched")
            return 0
        n, s2 = _patch_list(s, regex)
        if n == 0:
            print(f"{path}: no '{regex.pattern[:30]}' match; "
                  f"trying other kleaf list form", file=sys.stderr)
            continue
        open(path, "w").write(s2)
        print(f"{path}: registered wireless modules with kleaf "
              f"({n} list(s) updated)")
        return 0
    print(f"{p}: no modules.bzl/BUILD.bazel kleaf module list found "
          f"(legacy build.sh?); nothing to register")
    return 0


if __name__ == "__main__":
    sys.exit(main())
