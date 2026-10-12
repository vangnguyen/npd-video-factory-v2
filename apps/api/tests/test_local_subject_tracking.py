import numpy as np
import pytest

from app.local_subject_tracking import TrackingConfiguration, LocalTemplateTrackingProvider, normalized_correlation


def tracker():
    return LocalTemplateTrackingProvider(TrackingConfiguration(seed_box={"x": .2, "y": .25, "width": .2, "height": .25}, search_radius=.3))


def image(x=16, y=16):
    value = np.full((64, 80), 30., dtype=np.float64)
    patch = np.random.default_rng(17).integers(50, 240, size=(16, 16))
    value[y:y + 16, x:x + 16] = patch
    return value


def test_fft_correlation_matches_independent_direct_window_formula():
    source = np.random.default_rng(47).integers(0, 256, size=(24, 32)).astype(float)
    patch = source[7:13, 11:19].copy()
    actual = normalized_correlation(source, patch)
    expected = np.empty_like(actual)
    centered = patch - patch.mean()
    for y in range(expected.shape[0]):
        for x in range(expected.shape[1]):
            window = source[y:y + 6, x:x + 8];window = window - window.mean()
            expected[y, x] = (window * centered).sum() / np.sqrt((window ** 2).sum() * (centered ** 2).sum())
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    assert np.unravel_index(actual.argmax(), actual.shape) == (7, 11)


def test_actual_pixel_translation_returns_source_normalized_positions_without_semantic_confidence():
    model = tracker();seed = model.observe(image(), 0)
    assert seed.status == "seed" and seed.confidence is None
    for ordinal in range(1, 5):
        result = model.observe(image(16 + ordinal * 3, 16 + ordinal), ordinal * .2)
        assert result.status == "tracked"
        assert result.bounding_box.x == (16 + ordinal * 3) / 80
        assert result.bounding_box.y == (16 + ordinal) / 64
        assert result.normalized_cross_correlation > .999
        assert result.confidence is None


def test_textureless_seed_and_disappearing_subject_do_not_invent_positions():
    model = tracker();assert model.observe(np.full((64, 80), 40.), 0).status == "low_texture"
    assert model.observe(image(), .2).status == "stopped_after_loss"
    model = tracker();model.observe(image(), 0)
    lost = model.observe(np.full((64, 80), 30.), .2)
    assert lost.status == "lost" and lost.bounding_box is None
    assert model.observe(image(20, 17), .4).status == "stopped_after_loss"


def test_identical_distractor_is_ambiguous_and_never_switches_subject():
    model = tracker();model.observe(image(), 0)
    value = image();value[16:32, 36:52] = image()[16:32, 16:32]
    result = model.observe(value, .2)
    assert result.status == "ambiguous" and result.bounding_box is None


@pytest.mark.parametrize("timestamp", [-1., float("nan"), 0.])
def test_invalid_or_repeated_timestamps_are_refused(timestamp):
    model = tracker();model.observe(image(), 0)
    with pytest.raises(ValueError):model.observe(image(), timestamp)


def test_changed_geometry_nonfinite_pixels_and_unresolvable_seed_are_refused():
    model = tracker();model.observe(image(), 0)
    with pytest.raises(ValueError):model.observe(np.zeros((80, 80)), .2)
    with pytest.raises(ValueError):tracker().observe(np.full((64, 80), np.nan), 0)
    model = LocalTemplateTrackingProvider(TrackingConfiguration(seed_box={"x": 0., "y": 0., "width": .01, "height": .01}))
    with pytest.raises(ValueError):model.observe(image(), 0)
