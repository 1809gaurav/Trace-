import struct
import unittest

from engine.fat32 import (
    FAT32_EOC_MIN,
    decode_directory_entry,
    follow_fat_chain,
    parse_boot_sector,
    select_boot_sector,
)


def make_boot_sector():
    sector = bytearray(512)
    struct.pack_into("<H", sector, 0x0B, 512)  # BPB_BytsPerSec @0x0B, 2 bytes LE
    sector[0x0D] = 2  # BPB_SecPerClus @0x0D, 1 byte
    struct.pack_into("<H", sector, 0x0E, 32)  # BPB_RsvdSecCnt @0x0E, 2 bytes LE
    sector[0x10] = 2  # BPB_NumFATs @0x10, 1 byte
    struct.pack_into("<I", sector, 0x20, 140000)  # BPB_TotSec32 @0x20, 4 bytes LE
    struct.pack_into("<I", sector, 0x24, 1024)  # BPB_FATSz32 @0x24, 4 bytes LE
    struct.pack_into("<I", sector, 0x2C, 2)  # BPB_RootClus @0x2C, 4 bytes LE
    sector[510:512] = b"\x55\xaa"  # BS_Signature @0x1FE, 2 bytes
    return sector


class BootSectorTests(unittest.TestCase):
    def test_parses_valid_fat32_bpb(self):
        boot = make_boot_sector()
        parsed = parse_boot_sector(boot, 140000 * 512)
        self.assertEqual(parsed.bytes_per_sector, 512)
        self.assertEqual(parsed.sectors_per_cluster, 2)
        self.assertEqual(parsed.root_cluster, 2)
        self.assertGreaterEqual(parsed.cluster_count, 65525)

    def test_backup_boot_sector_is_used_when_primary_is_invalid(self):
        image = bytearray(7 * 512 + 512)
        image[6 * 512:7 * 512] = make_boot_sector()
        parsed, source = select_boot_sector(image, 140000 * 512)
        self.assertEqual(source, "backup")
        self.assertEqual(parsed.root_cluster, 2)

    def test_rejects_non_fat32_and_sanity_errors(self):
        boot = make_boot_sector()
        boot[510:512] = b"\x00\x00"  # BS_Signature @0x1FE, 2 bytes
        with self.assertRaises(ValueError):
            parse_boot_sector(boot, 140000 * 512)

        boot = make_boot_sector()
        boot[0x0D] = 3  # BPB_SecPerClus @0x0D, 1 byte
        with self.assertRaises(ValueError):
            parse_boot_sector(boot, 140000 * 512)

    def test_reports_cluster_count_that_is_too_small_for_fat32(self):
        boot = make_boot_sector()
        struct.pack_into("<I", boot, 0x20, 100000)  # BPB_TotSec32 @0x20, 4 bytes LE
        with self.assertRaisesRegex(ValueError, "at least 65525 data clusters.*yield only"):
            parse_boot_sector(boot, 100000 * 512)

    def test_reports_partitioned_disk_image(self):
        image = bytearray(100000 * 512)
        image[510:512] = b"\x55\xaa"  # MBR signature @0x1FE, 2 bytes
        image[446 + 4] = 0x0C  # MBR partition type @0x1C2, 1 byte
        struct.pack_into("<I", image, 446 + 8, 2048)  # MBR partition start LBA @0x1C6, 4 bytes LE
        struct.pack_into("<I", image, 446 + 12, 90000)  # MBR partition size @0x1CA, 4 bytes LE
        with self.assertRaisesRegex(ValueError, "partitioned disk image detected.*sector 2048"):
            select_boot_sector(image, len(image))


class DirectoryEntryTests(unittest.TestCase):
    def test_deleted_short_name_and_fat_timestamps(self):
        raw = bytearray(32)
        raw[0:11] = b"\xe5ILE    JPG"  # DIR_Name @0x00, 11 bytes
        raw[11] = 0x20  # DIR_Attr @0x0B, 1 byte
        struct.pack_into("<H", raw, 14, (10 << 11) | (30 << 5) | 14)  # DIR_CrtTime @0x0E
        raw[13] = 50  # DIR_CrtTimeTenth @0x0D, 1 byte
        struct.pack_into("<H", raw, 16, (2026 - 1980) << 9 | 1 << 5 | 1)  # DIR_CrtDate @0x10
        struct.pack_into("<H", raw, 18, (2026 - 1980) << 9 | 1 << 5 | 1)  # DIR_LstAccDate @0x12
        struct.pack_into("<H", raw, 22, (10 << 11) | (30 << 5) | 14)  # DIR_WrtTime @0x16
        struct.pack_into("<H", raw, 24, (2026 - 1980) << 9 | 1 << 5 | 1)  # DIR_WrtDate @0x18
        struct.pack_into("<H", raw, 20, 0)  # DIR_FstClusHI @0x14, 2 bytes LE
        struct.pack_into("<H", raw, 26, 7)  # DIR_FstClusLO @0x1A, 2 bytes LE
        struct.pack_into("<I", raw, 28, 12)  # DIR_FileSize @0x1C, 4 bytes LE

        entry = decode_directory_entry(raw)
        self.assertTrue(entry.deleted)
        self.assertEqual(entry.name, "_ILE.JPG")
        self.assertEqual(entry.start_cluster, 7)
        self.assertEqual(entry.timestamps["created"], "2026-01-01T10:30:28.500000Z")
        self.assertEqual(entry.timestamps["accessed"], "2026-01-01T00:00:00Z")

    def test_follow_fat_chain_stops_at_eoc_and_tolerates_loops(self):
        fat = bytearray(64)
        struct.pack_into("<I", fat, 3 * 4, 4)  # FAT entry @cluster*4, 4 bytes LE
        struct.pack_into("<I", fat, 4 * 4, FAT32_EOC_MIN)  # FAT entry @cluster*4, 4 bytes LE
        clusters, warnings = follow_fat_chain(fat, 3, 10)
        self.assertEqual(clusters, [3, 4])
        self.assertEqual(warnings, [])

        struct.pack_into("<I", fat, 4 * 4, 3)  # FAT entry @cluster*4, 4 bytes LE
        clusters, warnings = follow_fat_chain(fat, 3, 10)
        self.assertEqual(clusters, [3, 4])
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
