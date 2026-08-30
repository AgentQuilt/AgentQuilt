"""The prefix half, without a database: rendering is a pure function of the fetch.

The port cannot make `layers` deterministic by signature alone (ADR-0027), so the
property is asserted here, over generated sources, for the `instructions` adapter.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.kernel.context.contributors import Instructions, InstructionsContributor
from app.kernel.ports.context_contributor import (
    EnvelopeContributor,
    Layer,
    PrefixContributor,
    PrefixProfile,
    Slice,
)
from tests.kit import StaticContributor

_PROFILES: tuple[PrefixProfile, ...] = ("personal", "space", "none")
_SOURCES = st.builds(
    Instructions,
    org_name=st.text(),
    agent_name=st.text(),
    agent_version=st.integers(min_value=1),
    soul_text=st.text(),
    profile=st.text(),
    prefix_profile=st.sampled_from(_PROFILES),
    principal_id=st.uuids(),
)


@given(source=_SOURCES, other=_SOURCES)
def test_layers_deterministic(source: Instructions, other: Instructions) -> None:
    """The same source renders the same bytes, and a layer's version moves
    whenever its body does, which is what makes `prefix_key` safe (ADR-0014)."""
    rendered = InstructionsContributor().layers(source)
    assert rendered == InstructionsContributor().layers(source)
    for first, second in zip(
        rendered, InstructionsContributor().layers(other), strict=True
    ):
        assert first.slot == second.slot
        if first.body != second.body:
            assert first.version != second.version


def test_static_contributor_satisfies_both_contracts() -> None:
    """One object on both protocols, which is what `skills` does for real; the
    annotations are the assertion, the slots only show the script reached it."""
    layers = (Layer(slot="L1", version="v1", body="one"),)
    slices = (Slice(slot="D1", body="two", provenance="ref", priority=1),)
    contributor = StaticContributor("test", layers, slices)
    prefix: PrefixContributor[tuple[Layer, ...]] = contributor
    envelope: EnvelopeContributor = contributor
    assert prefix.prefix_slots == ("L1",)
    assert envelope.envelope_slots == ("D1",)
