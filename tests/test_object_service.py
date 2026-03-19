import unittest

from models.rect_prism import RectPrism
from services.object_service import ObjectService


class _FakeInputService:
    def __init__(self):
        self.controlled_object = None

    def set_controlled_object(self, obj):
        self.controlled_object = obj


class ObjectServiceTests(unittest.TestCase):
    def test_add_remove_and_controlled_object_flow(self):
        input_service = _FakeInputService()
        service = ObjectService(input_service=input_service)

        obj_a = RectPrism(name="A", colour=(1.0, 0.0, 0.0, 0.2))
        obj_b = RectPrism(name="B", colour=(0.0, 1.0, 0.0, 0.8))
        obj_c = RectPrism(name="C", colour=(0.0, 0.0, 1.0, 0.5))

        service.add_object(obj_a)
        service.add_object(obj_b)
        service.add_object(obj_c)

        # Objects are sorted by alpha descending in add_object
        self.assertEqual([o.name for o in service.get_objects()], ["B", "C", "A"])

        service.set_controlled_object(name="C")
        self.assertIs(service.get_controlled_object(), obj_c)
        self.assertIs(input_service.controlled_object, obj_c)

        service.clear_controlled_object()
        self.assertIsNone(service.get_controlled_object())
        self.assertIsNone(input_service.controlled_object)

        service.remove_object(name="B")
        self.assertIsNone(service.get_object("B"))
        self.assertEqual(len(service.get_objects()), 2)


if __name__ == "__main__":
    unittest.main()
