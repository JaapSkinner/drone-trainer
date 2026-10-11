import unittest

from models.grid import Grid
from models.rect_prism import RectPrism
from services.object_service import ObjectService


class _FakeInputService:
    def __init__(self):
        self.controlled_object = None

    def set_controlled_object(self, obj):
        self.controlled_object = obj


class _Recorder:
    def __init__(self, service):
        self.events = []
        service.object_added.connect(lambda o: self.events.append(("added", o.name)))
        service.object_removed.connect(lambda o: self.events.append(("removed", o.name)))
        service.object_changed.connect(lambda o: self.events.append(("changed", o.name)))
        service.objects_changed.connect(lambda: self.events.append(("structure",)))
        service.controlled_object_changed.connect(
            lambda o: self.events.append(("controlled", o.name if o else None)))


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

        # Insertion order is preserved (the renderer handles translucency order)
        self.assertEqual([o.name for o in service.get_objects()], ["A", "B", "C"])

        service.set_controlled_object(name="C")
        self.assertIs(service.get_controlled_object(), obj_c)
        self.assertIs(input_service.controlled_object, obj_c)

        service.clear_controlled_object()
        self.assertIsNone(service.get_controlled_object())
        self.assertIsNone(input_service.controlled_object)

        service.remove_object(name="B")
        self.assertIsNone(service.get_object("B"))
        self.assertEqual(len(service.get_objects()), 2)

    def test_names_are_made_unique(self):
        service = ObjectService()
        first = service.add_object(RectPrism(name="Box"))
        second = service.add_object(RectPrism(name="Box"))
        third = service.add_object(RectPrism(name="Box"))
        self.assertEqual([first.name, second.name, third.name], ["Box", "Box 2", "Box 3"])
        self.assertEqual(service.rename_object(third, "Box"), "Box 3")
        self.assertEqual(service.rename_object(third, "Crate"), "Crate")

    def test_structural_changes_emit_signals(self):
        service = ObjectService()
        rec = _Recorder(service)
        box = service.add_object(RectPrism(name="Box"))
        service.notify_object_changed(box)
        service.remove_object(obj=box)
        self.assertEqual(rec.events, [
            ("added", "Box"), ("structure",),
            ("changed", "Box"),
            ("removed", "Box"), ("structure",),
        ])

    def test_removing_the_controlled_object_clears_control(self):
        input_service = _FakeInputService()
        service = ObjectService(input_service=input_service)
        rec = _Recorder(service)
        box = service.add_object(RectPrism(name="Box"))
        service.set_controlled_object(obj=box)
        service.remove_object(obj=box)
        self.assertIsNone(service.get_controlled_object())
        self.assertIsNone(input_service.controlled_object)
        self.assertIn(("controlled", None), rec.events)

    def test_non_controllable_objects_cannot_be_controlled(self):
        service = ObjectService()
        grid = service.add_object(Grid(name="Grid"))
        service.set_controlled_object(obj=grid)
        self.assertIsNone(service.get_controlled_object())

    def test_clear_can_keep_helpers(self):
        service = ObjectService()
        service.add_objects([Grid(name="Grid"), RectPrism(name="A"), RectPrism(name="B")])
        service.clear_objects(keep=lambda o: o.helper)
        self.assertEqual([o.name for o in service.get_objects()], ["Grid"])

    def test_tracking_poses_apply_to_matching_unlocked_objects(self):
        service = ObjectService()
        tracked = service.add_object(RectPrism(name="Drone"))
        tracked.set_tracked(True, "cf1")
        locked = service.add_object(RectPrism(name="Locked"))
        locked.set_tracked(True, "cf2")
        locked.pose_locked = True
        untracked = service.add_object(RectPrism(name="Static"))
        untracked.tracking_id = "cf3"  # has an ID but tracking is off

        pose = (1.0, 2.0, 3.0, 1.0, 0.0, 0.0, 0.0)
        moved = service.apply_tracking_poses({"cf1": pose, "cf2": pose, "cf3": pose})

        self.assertEqual(moved, 1)
        self.assertEqual(tracked.pose, pose)
        self.assertNotEqual(locked.pose, pose)
        self.assertIsNotNone(locked.last_tracking_update)  # still seen, just not moved
        self.assertNotEqual(untracked.pose, pose)
        self.assertLess(tracked.tracking_age(), 1.0)

    def test_tracking_requires_an_id(self):
        box = RectPrism(name="Box")
        with self.assertRaises(ValueError):
            box.set_tracked(True)


if __name__ == "__main__":
    unittest.main()
