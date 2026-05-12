from __future__ import annotations

from app.pdf_utils import _clamp_bbox_to_page, _extract_page_content


class FakeTable:
    def __init__(self, bbox, rows):
        self.bbox = bbox
        self._rows = rows

    def extract(self):
        return self._rows


class FakePage:
    def __init__(self):
        self.bbox = (0.0, 0.0, 1920.0, 1080.0)
        self.page_number = 1
        self._tables = [
            FakeTable(
                (-0.00012499999999704414, 0.0, 1920.00005, 1080.0),
                [["A", "B"], ["1", "2"]],
            )
        ]
        self.seen_bboxes = []

    def find_tables(self):
        return self._tables

    def outside_bbox(self, bbox):
        self.seen_bboxes.append(bbox)
        px0, py0, px1, py1 = self.bbox
        x0, y0, x1, y1 = bbox
        if not (px0 <= x0 <= x1 <= px1 and py0 <= y0 <= y1 <= py1):
            raise ValueError(
                f"Bounding box {bbox} is not fully within parent page bounding box {self.bbox}"
            )
        return self

    def extract_text(self):
        return "page text"


def test_clamp_bbox_to_page_bounds():
    bbox = (-0.00012499999999704414, 0.0, 1920.00005, 1080.0)
    page_bbox = (0.0, 0.0, 1920.0, 1080.0)

    assert _clamp_bbox_to_page(bbox, page_bbox) == (0.0, 0.0, 1920.0, 1080.0)


def test_extract_page_content_clamps_table_bbox_before_outside_bbox():
    page = FakePage()

    page_text, tables = _extract_page_content(page)

    assert page_text == "page text"
    assert tables == [[["A", "B"], ["1", "2"]]]
    assert page.seen_bboxes == [(0.0, 0.0, 1920.0, 1080.0)]
