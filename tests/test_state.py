import pytest

from mcp_irve.errors import EtatManquantError
from mcp_irve.models import PointGeo
from mcp_irve.state import SessionState, Stage, get_state, require_stage


def test_get_state_returns_same_instance_for_same_session_id():
    a = get_state("test-session-1")
    b = get_state("test-session-1")
    assert a is b


def test_get_state_returns_distinct_instances_for_distinct_sessions():
    a = get_state("test-session-2")
    b = get_state("test-session-3")
    assert a is not b


def test_new_state_starts_empty():
    state = SessionState()
    assert state.stage is Stage.EMPTY
    assert state.point_depart is None
    assert state.reseau_bt == []
    assert state.reseau_routier == []
    assert state.candidats == []
    assert state.resultat is None


def test_reset_clears_downstream_state_and_bumps_version():
    state = SessionState()
    state.stage = Stage.CANDIDATS_FILTRES
    state.point_depart = PointGeo(lat=48.85, lon=2.35, x_l93=652000.0, y_l93=6862000.0)
    state.adresse_normalisee = "1 rue de Test, 75000 Paris"
    state.reseau_bt = ["placeholder"]  # type: ignore[list-item]
    state.buffer_m = 10
    state.buffer_zone = "placeholder"  # type: ignore[assignment]
    version_before = state.version

    state.reset()

    assert state.stage is Stage.EMPTY
    assert state.point_depart is None
    assert state.buffer_m is None
    assert state.buffer_zone is None
    assert state.adresse_normalisee is None
    assert state.reseau_bt == []
    assert state.version == version_before + 1


@pytest.mark.parametrize(
    "current,required",
    [
        (Stage.EMPTY, Stage.GEOCODED),
        (Stage.GEOCODED, Stage.RESEAU_BT),
        (Stage.RESEAU_ROUTIER, Stage.CANDIDATS_FILTRES),
        (Stage.EMPTY, Stage.RESULTAT),
    ],
)
def test_require_stage_raises_when_stage_not_reached(current, required):
    state = SessionState()
    state.stage = current
    with pytest.raises(EtatManquantError):
        require_stage(state, required)


def test_require_stage_error_names_the_missing_tool():
    state = SessionState()
    state.stage = Stage.RESEAU_BT
    with pytest.raises(EtatManquantError, match="recuperer_reseau_routier"):
        require_stage(state, Stage.RESEAU_ROUTIER)


@pytest.mark.parametrize(
    "current,required",
    [
        (Stage.GEOCODED, Stage.GEOCODED),
        (Stage.RESULTAT, Stage.GEOCODED),
        (Stage.RESULTAT, Stage.RESULTAT),
    ],
)
def test_require_stage_passes_when_stage_reached_or_exceeded(current, required):
    state = SessionState()
    state.stage = current
    require_stage(state, required)  # ne doit pas lever
