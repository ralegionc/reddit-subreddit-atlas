"""Design tokens. Values and slot order come from the dataviz reference palette;
the 3-hue categorical caps and the sequential ramp were re-validated for this
project with scripts/validate_palette.js under --pairs all (scatter form).
"""

SURFACE_DARK = "#1a1a19"
SURFACE_LIGHT = "#fcfcfb"

INK = {
    "dark": {"primary": "#ffffff", "secondary": "#c3c2b7", "muted": "#7d7c74"},
    "light": {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#8a8983"},
}

# Scatter forms are gated on all-pairs CVD separation, where only the first
# three slots clear the floors. Anything past three folds to "Other" or facets.
CATEGORICAL = {
    "dark": ["#3987e5", "#d95926", "#199e70"],
    "light": ["#2a78d6", "#eb6834", "#1baf7a"],
}

# Sequential blue, light -> dark (steps 100..700 of the reference ramp).
SEQ_BLUE = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]


def seq_cmap(mode: str = "dark"):
    """On a dark surface the ramp is reversed so 'near zero' recedes toward the
    surface rather than glowing brightest."""
    from matplotlib.colors import LinearSegmentedColormap

    steps = SEQ_BLUE[::-1] if mode == "dark" else SEQ_BLUE
    return LinearSegmentedColormap.from_list(f"seqblue_{mode}", steps)
