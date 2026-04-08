import unittest

from scrapers.rmp import teacher_gid_from_legacy


class TeacherGidTests(unittest.TestCase):
    def test_encodes_known_id(self):
        # base64("Teacher-12345")
        self.assertEqual(teacher_gid_from_legacy(12345), "VGVhY2hlci0xMjM0NQ==")

    def test_accepts_string_ids(self):
        self.assertEqual(teacher_gid_from_legacy("12345"), teacher_gid_from_legacy(12345))

    def test_different_ids_give_different_gids(self):
        self.assertNotEqual(teacher_gid_from_legacy(1), teacher_gid_from_legacy(2))
