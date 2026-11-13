"""Validated game data snapshot. Loaded from a repository, never from service files."""

from copy import deepcopy
from dataclasses import dataclass
from functools import cached_property

DEFAULT_CAPACITY = 5
MIN_PLAYERS = 2
ROUND_SECONDS = 90
LEGACY_ROOM = "BENGER"
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SUPPORTED_POWERS = frozenset(("double", "block", "shield", "bank", "bonus"))


@dataclass(frozen=True)
class GameCatalog:
    modes: dict
    mix_modes: tuple[str, ...]
    powers: dict

    @classmethod
    def from_dict(cls, data):
        def require(condition, field):
            if not condition:
                raise ValueError("Invalid catalogue: " + field)

        require(isinstance(data, dict), "expected mapping")
        modes, mix, powers = data.get("modes"), data.get("mix"), data.get("powers")
        require(isinstance(modes, dict) and bool(modes), "modes")
        require(
            isinstance(mix, list)
            and bool(mix)
            and all(isinstance(v, str) and v in modes for v in mix),
            "mix",
        )
        require(len(set(mix)) == len(mix), "mix duplicates")
        require(
            isinstance(powers, dict) and set(powers) == SUPPORTED_POWERS,
            "powers must match implemented rules",
        )
        ids = set()
        for name, mode in modes.items():
            label = "modes." + str(name)
            require(
                isinstance(name, str) and 0 < len(name) <= 63 and name != "mix", label
            )
            require(isinstance(mode, dict), label)
            for field in ("title", "description", "icon", "tone"):
                require(
                    isinstance(mode.get(field), str) and bool(mode[field].strip()),
                    label + "." + field,
                )
                if field in ("title", "icon", "tone"):
                    require(
                        len(mode[field])
                        <= {"title": 200, "icon": 32, "tone": 32}[field],
                        label + "." + field + " too long",
                    )
            require(
                mode.get("kind") in ("text", "image", "shared", "relay"),
                label + ".kind",
            )
            require(
                isinstance(mode.get("prompts"), list) and bool(mode["prompts"]),
                label + ".prompts",
            )
            fields = mode.get("fields", [])
            require(
                isinstance(fields, list)
                and all(isinstance(v, str) and bool(v.strip()) for v in fields),
                label + ".fields",
            )
            for prompt in mode["prompts"]:
                require(isinstance(prompt, dict), label + ".prompts")
                identifier = prompt.get("id")
                require(
                    isinstance(identifier, str) and 0 < len(identifier) <= 128,
                    label + ".prompt.id",
                )
                require(identifier not in ids, "duplicate prompt id " + str(identifier))
                ids.add(identifier)
                for field in ("prompt", "context"):
                    require(
                        isinstance(prompt.get(field), str)
                        and bool(prompt[field].strip()),
                        label + ".prompt." + field,
                    )
                if mode["kind"] == "shared":
                    require(
                        isinstance(prompt.get("scene"), str)
                        and bool(prompt["scene"].strip()),
                        label + ".prompt.scene",
                    )
                for field in ("twists", "answers"):
                    if field in prompt:
                        require(
                            isinstance(prompt[field], list)
                            and all(isinstance(v, str) for v in prompt[field]),
                            label + ".prompt." + field,
                        )
                require(
                    set(prompt)
                    <= {"id", "prompt", "context", "scene", "twists", "answers"},
                    label + ".prompt unknown field",
                )
        for key, power in powers.items():
            require(isinstance(power, dict), "powers." + key)
            for field in ("title", "description", "icon"):
                require(
                    isinstance(power.get(field), str) and bool(power[field].strip()),
                    "powers." + key + "." + field,
                )
                if field in ("title", "icon"):
                    require(
                        len(power[field]) <= {"title": 200, "icon": 32}[field],
                        "powers." + key + "." + field + " too long",
                    )
        return cls(
            deepcopy(modes),
            tuple(mix),
            {
                key: [row[field] for field in ("title", "description", "icon")]
                for key, row in powers.items()
            },
        )

    @cached_property
    def prompts(self):
        return {key: mode["prompts"] for key, mode in self.modes.items()}

    @cached_property
    def mode_info(self):
        return {
            key: [mode[field] for field in ("title", "description", "icon", "tone")]
            for key, mode in self.modes.items()
        }

    @cached_property
    def image_modes(self):
        return {
            key
            for key, mode in self.modes.items()
            if mode["kind"] in ("image", "relay")
        }
