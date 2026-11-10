"""
Unit & Integration Tests - Company Directory Provider
Kiểm thử danh bạ công ty niêm yết (HOSE, HNX, UPCoM):
- search_companies:
  + Tìm kiếm chính xác mã (exact match)
  + Tìm kiếm theo tiền tố mã (prefix match)
  + Tìm kiếm không dấu / tiếng Việt (nameVi, nameUnaccent)
  + Giới hạn số lượng kết quả (limit)
  + Xử lý chuỗi rỗng / ký tự đặc biệt (edge cases)
"""

import os
import unittest

os.environ['APP_ENV'] = 'testing'

from backend.data_providers.company_directory_provider import (
    search_companies,
    _strip_vietnamese_accents,
)


class TestCompanyDirectoryProvider(unittest.TestCase):
    """Kiểm thử bộ tìm kiếm danh bạ công ty."""

    def test_strip_vietnamese_accents(self):
        text = "Tập đoàn Hòa Phát"
        unaccent = _strip_vietnamese_accents(text)
        self.assertEqual(unaccent, "Tap doan Hoa Phat")

    def test_search_companies_empty_and_special_chars(self):
        # Truy vấn rỗng
        self.assertEqual(search_companies(''), [])
        self.assertEqual(search_companies('   '), [])

        # Ký tự regex đặc biệt không gây crash
        res = search_companies('***')
        self.assertIsInstance(res, list)

    def test_search_exact_and_prefix(self):
        # Tìm chính xác HPG
        res = search_companies('HPG', limit=5)
        self.assertGreater(len(res), 0)
        self.assertEqual(res[0]['ticker'], 'HPG')

        # Tìm tiền tố "HP"
        res_prefix = search_companies('HP', limit=5)
        self.assertGreater(len(res_prefix), 0)
        self.assertTrue(any(c['ticker'].startswith('HP') for c in res_prefix))

    def test_search_vietnamese_name(self):
        # Tìm theo tên tiếng Việt có dấu
        res = search_companies('Hòa Phát', limit=5)
        self.assertGreater(len(res), 0)
        self.assertTrue(any(c['ticker'] == 'HPG' for c in res))

        # Tìm theo tên không dấu
        res_unaccent = search_companies('hoa phat', limit=5)
        self.assertGreater(len(res_unaccent), 0)
        self.assertTrue(any(c['ticker'] == 'HPG' for c in res_unaccent))

    def test_search_limit_enforced(self):
        res = search_companies('a', limit=3)
        self.assertLessEqual(len(res), 3)


if __name__ == '__main__':
    unittest.main()

