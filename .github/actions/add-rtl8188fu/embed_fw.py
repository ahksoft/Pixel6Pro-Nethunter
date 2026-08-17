#!/usr/bin/env python3
"""Embed rtlwifi/rtl8188fufw.bin into the rtl8188fu module.

Generates embedded_fw.c from the driver's firmware file and patches the
driver source so rtl8188f_FirmwareDownload() uses the embedded copy instead
of request_firmware(). This makes the .ko self-contained on Android, where
/vendor/firmware is read-only and FW_LOADER_USER_HELPER_FALLBACK is off.

Idempotent: safe to run repeatedly.
"""
import os
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: embed_fw.py <driver-dir>", file=sys.stderr)
        return 1
    d = os.path.abspath(sys.argv[1])
    fw = os.path.join(d, "firmware", "rtl8188fufw.bin")
    hal = os.path.join(d, "hal", "rtl8188f", "rtl8188f_hal_init.c")
    mk = os.path.join(d, "Makefile")
    for p in (fw, hal, mk):
        if not os.path.isfile(p):
            print(f"error: {p} not found", file=sys.stderr)
            return 1

    data = open(fw, "rb").read()
    print(f"rtl8188fufw.bin: {len(data)} bytes")

    # 1) Generate embedded_fw.c
    out = os.path.join(d, "embedded_fw.c")
    with open(out, "w") as f:
        f.write("#include <linux/firmware.h>\n")
        f.write("#include <linux/types.h>\n\n")
        f.write(f"/* Embedded RTL8188FU firmware (rtlwifi/rtl8188fufw.bin), {len(data)} bytes. */\n")
        f.write("static const u8 rtl8188fufw_bin[] __aligned(4) = {\n")
        for i in range(0, len(data), 16):
            chunk = data[i : i + 16]
            f.write("\t" + ", ".join("0x%02x" % b for b in chunk) + ",\n")
        f.write("};\n\n")
        f.write("const struct firmware rtl8188fu_embedded_fw = {\n")
        f.write("\t.size = sizeof(rtl8188fufw_bin),\n")
        f.write("\t.data = rtl8188fufw_bin,\n")
        f.write("};\n")
    print(f"wrote {out}")

    # 2) Patch rtl8188f_hal_init.c
    src = open(hal).read()
    if "CONFIG_RTL8188FU_EMBEDDED_FW" in src:
        print("hal_init.c: already patched, skipping")
    else:
        req_old = (
            '\tdev_info(&psdpriv->pusbdev->dev, "request firmware %s\\n",fw_name);\n'
            "\tif (request_firmware(&fw, fw_name, &psdpriv->pusbdev->dev)) {\n"
            '\t\tdev_err(&psdpriv->pusbdev->dev, "Firmware %s not available\\n", fw_name);\n'
            "\t\tgoto exit;\n"
            "\t}\n"
            "\n"
            '\tdev_info(&psdpriv->pusbdev->dev, "request firmware %s loaded\\n",fw_name);\n'
        )
        req_new = (
            "#ifdef CONFIG_RTL8188FU_EMBEDDED_FW\n"
            "\textern const struct firmware rtl8188fu_embedded_fw;\n"
            '\tdev_info(&psdpriv->pusbdev->dev, "rtl8188fu: using embedded firmware %s\\n", fw_name);\n'
            "\tfw = &rtl8188fu_embedded_fw;\n"
            "#else\n"
            + req_old +
            "#endif\n"
        )
        if req_old not in src:
            print("error: request_firmware block not found in hal_init.c", file=sys.stderr)
            return 1
        src = src.replace(req_old, req_new, 1)

        rel_old = "exit:\n\trelease_firmware(fw);\n"
        rel_new = (
            "exit:\n"
            "#ifndef CONFIG_RTL8188FU_EMBEDDED_FW\n"
            "\trelease_firmware(fw);\n"
            "#endif\n"
        )
        if rel_old not in src:
            print("error: release_firmware block not found in hal_init.c", file=sys.stderr)
            return 1
        src = src.replace(rel_old, rel_new, 1)
        open(hal, "w").write(src)
        print("hal_init.c: patched")

    # 3) Patch Makefile
    mk_src = open(mk).read()
    if "-DCONFIG_RTL8188FU_EMBEDDED_FW" in mk_src:
        print("Makefile: already patched, skipping")
    else:
        anchor = "EXTRA_CFLAGS += $(USER_EXTRA_CFLAGS)\n"
        if anchor not in mk_src:
            print("error: EXTRA_CFLAGS anchor not found in Makefile", file=sys.stderr)
            return 1
        mk_src = mk_src.replace(
            anchor,
            anchor + "EXTRA_CFLAGS += -DCONFIG_RTL8188FU_EMBEDDED_FW\n",
            1,
        )
        obj_anchor = (
            "rtl8188fu-$(CONFIG_MP_INCLUDED) += core/rtw_mp.o \\\n"
            "\t\t\t\t\tcore/rtw_mp_ioctl.o\n"
        )
        if obj_anchor not in mk_src:
            print("error: obj anchor not found in Makefile", file=sys.stderr)
            return 1
        mk_src = mk_src.replace(
            obj_anchor, obj_anchor + "\nrtl8188fu-y += embedded_fw.o\n", 1
        )
        open(mk, "w").write(mk_src)
        print("Makefile: patched")

    # 4) Absolute include paths for in-tree (kleaf) builds. The driver's own
    #    EXTRA_CFLAGS '-I$(src)/...' are relative to the objtree, which does
    #    not resolve inside the bazel out-of-tree objtree. Standalone M= builds
    #    keep using the driver's own flags. Also disable -Werror for the module:
    #    the old Realtek code trips clang warnings (uninitialized, header-guard)
    #    that GKI turns into errors.
    if "ccflags-y += -Wno-error" not in mk_src:
        cc_anchor = "ccflags-y += $(EXTRA_CFLAGS)\n"
        if cc_anchor not in mk_src:
            print("error: ccflags-y anchor not found in Makefile", file=sys.stderr)
            return 1
        mk_src = mk_src.replace(
            cc_anchor,
            cc_anchor + "ccflags-y += -Wno-error\n",
            1,
        )
        open(mk, "w").write(mk_src)
        print("Makefile: added -Wno-error")

    if "KBUILD_EXTMOD" not in mk_src:
        inc_block = (
            "\n# In-tree (kleaf) builds: $(src) is relative to the objtree; use\n"
            "# absolute paths based on $(srctree) instead.\n"
            "ifneq ($(KBUILD_EXTMOD),)\n"
            "ccflags-y += -I$(M)/include -I$(M)/hal/phydm -I$(M)/hal/btc\n"
            "else\n"
            "ccflags-y += -I$(srctree)/$(src)/include -I$(srctree)/$(src)/hal/phydm -I$(srctree)/$(src)/hal/btc\n"
            "endif\n"
        )
        cc_anchor = "ccflags-y += $(EXTRA_CFLAGS)\n"
        if cc_anchor not in mk_src:
            print("error: ccflags-y anchor not found in Makefile", file=sys.stderr)
            return 1
        mk_src = open(mk).read()
        mk_src = mk_src.replace(cc_anchor, cc_anchor + inc_block, 1)
        open(mk, "w").write(mk_src)
        print("Makefile: added in-tree include paths")

    # 5) Fix known clang -Werror bugs in the driver source (GKI builds with
    #    Werror). These are real bugs, not just warnings:
    #    - rtw_recv.h: get_rxbuf_desc()/pkt_to_recvframe() return pointers that
    #      are only assigned inside '#ifdef PLATFORM_WINDOWS', so on Linux they
    #      are used uninitialized.
    #    - phydm_features.h: #define guard name doesn't match the #ifndef guard.
    #    '-Wno-error' (section 4) is kept as a safety net for any other old
    #    Realtek warnings under clang.
    recv = os.path.join(d, "include", "rtw_recv.h")
    recv_src = open(recv).read()
    if "_buffer * buf_desc = NULL;" not in recv_src:
        recv_src = recv_src.replace(
            "_buffer * buf_desc;", "_buffer * buf_desc = NULL;", 1
        )
        open(recv, "w").write(recv_src)
        print("rtw_recv.h: fixed get_rxbuf_desc() uninitialized buf_desc")
    if "u8 * buf_star = NULL;" not in recv_src:
        recv_src = recv_src.replace(
            "u8 * buf_star;", "u8 * buf_star = NULL;", 1
        )
        open(recv, "w").write(recv_src)
        print("rtw_recv.h: fixed pkt_to_recvframe() uninitialized buf_star")

    feat = os.path.join(d, "hal", "phydm", "phydm_features.h")
    feat_src = open(feat).read()
    if "#define __PHYDM_FEATURES_H__\n" not in feat_src:
        feat_src = feat_src.replace("#define __PHYDM_FEATURES\n", "#define __PHYDM_FEATURES_H__\n", 1)
        open(feat, "w").write(feat_src)
        print("phydm_features.h: fixed header guard mismatch")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
