import unittest

from simulate_occupancy import get_occupied_utility_types, get_room_capacity


class OccupancySimulationTests(unittest.TestCase):
    def test_supported_utility_types_include_oku_and_baby_diaper(self):
        supported_types = get_occupied_utility_types()
        self.assertIn("restroom", supported_types)
        self.assertIn("baby_diaper", supported_types)
        self.assertIn("oku", supported_types)

    def test_oku_has_single_room_capacity_and_baby_diaper_has_three(self):
        self.assertEqual(get_room_capacity("oku"), 1)
        self.assertEqual(get_room_capacity("baby_diaper"), 3)


if __name__ == "__main__":
    unittest.main()
