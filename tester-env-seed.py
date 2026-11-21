# Deterministic product data for the Flagsmith tester-env baseline.
#
# Run inside the app container after the upstream e2e teardown seed:
#   python manage.py shell -c "exec(open('/tmp/tester-env-seed.py').read())"
#
# The upstream teardown deletes the e2e users' organisations (and therefore every
# project, feature, segment and identity under them), so this script only adds
# the baseline product state and never has to clean up after itself. All dates
# are pinned so list sorting and date columns are stable between resets.
import datetime as dt

from core.constants import BOOLEAN, INTEGER, STRING
from environments.identities.models import Identity
from environments.identities.traits.models import Trait
from features.models import Feature
from flag_engine.segments import constants as segment_constants
from projects.models import Project
from projects.tags.models import Tag
from segments.models import Condition, Segment, SegmentRule

PROJECT_NAME = "My Test Project"
UTC = dt.timezone.utc


def ts(value):
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


# Tag filter counts: checkout 3, experiment 3, mobile 3, pricing 2.
TAGS = [
    ("checkout", "#1F7A8C"),
    ("experiment", "#00B894"),
    ("mobile", "#6C5CE7"),
    ("pricing", "#E17055"),
]

# (enabled, value type, value) per environment. 7 enabled / 1 disabled in
# Development, 3 enabled / 5 disabled in Production.
FEATURES = [
    {
        "name": "checkout_v2",
        "description": "Two-step checkout with saved payment methods.",
        "created": ts("2026-09-14 09:30"),
        "tags": ["checkout", "experiment"],
        "states": {
            "Development": (True, "boolean", "true"),
            "Production": (False, "boolean", "true"),
        },
    },
    {
        "name": "seat_map_enabled",
        "description": "Interactive seat map on the booking page.",
        "created": ts("2026-09-21 14:05"),
        "tags": ["checkout", "mobile"],
        "states": {
            "Development": (True, "boolean", "true"),
            "Production": (True, "boolean", "true"),
        },
    },
    {
        "name": "max_seats_per_booking",
        "description": "Maximum seats a single booking may hold.",
        "created": ts("2026-10-02 11:15"),
        "tags": ["pricing"],
        "states": {
            "Development": (True, "integer", "6"),
            "Production": (True, "integer", "4"),
        },
    },
    {
        "name": "loyalty_points_multiplier",
        "description": "Points earned per pound spent by loyalty tier.",
        "created": ts("2026-10-09 08:45"),
        "tags": ["pricing", "experiment"],
        "states": {
            "Development": (True, "integer", "2"),
            "Production": (False, "integer", "1"),
        },
    },
    {
        "name": "checkout_copy_variant",
        "description": "Checkout call-to-action copy under test.",
        "created": ts("2026-10-16 16:20"),
        "tags": ["checkout", "experiment"],
        "states": {
            "Development": (True, "string", "one-tap"),
            "Production": (False, "string", "control"),
        },
    },
    {
        "name": "journey_planner_config",
        "description": "Journey planner connection limits per channel.",
        "created": ts("2026-10-23 10:10"),
        "tags": ["mobile"],
        "states": {
            "Development": (
                True,
                "string",
                '{"max_connections": 2, "prefer_rail": true}',
            ),
            "Production": (
                False,
                "string",
                '{"max_connections": 1, "prefer_rail": false}',
            ),
        },
    },
    {
        "name": "delay_notification_threshold_minutes",
        "description": "Delay in minutes before a push notification is sent.",
        "created": ts("2026-11-03 13:40"),
        "tags": ["mobile"],
        "states": {
            "Development": (True, "integer", "10"),
            "Production": (True, "integer", "15"),
        },
    },
    {
        "name": "duty_free_catalogue",
        "description": "Onboard duty-free catalogue for long-haul services.",
        "created": ts("2026-11-10 09:05"),
        "tags": [],
        "states": {
            "Development": (False, "string", '{"enabled_categories": []}'),
            "Production": (False, "string", '{"enabled_categories": []}'),
        },
    },
]

SEGMENTS = [
    {
        "name": "Loyalty Members",
        "description": "Travellers on the gold loyalty tier.",
        "conditions": [("plan", segment_constants.EQUAL, "gold")],
    },
    {
        "name": "UK Frequent Travellers",
        "description": "United Kingdom customers with five or more bookings.",
        "conditions": [
            ("country", segment_constants.EQUAL, "GB"),
            ("bookings", segment_constants.GREATER_THAN_INCLUSIVE, "5"),
        ],
    },
]

IDENTITIES = [
    {
        "identifier": "identity-1042",
        "traits": [
            ("plan", STRING, "gold"),
            ("country", STRING, "GB"),
            ("bookings", INTEGER, 12),
            ("newsletter", BOOLEAN, True),
        ],
    },
    {
        "identifier": "identity-2087",
        "traits": [
            ("plan", STRING, "silver"),
            ("country", STRING, "US"),
            ("bookings", INTEGER, 2),
            ("newsletter", BOOLEAN, False),
        ],
    },
    {
        "identifier": "identity-3311",
        "traits": [
            ("plan", STRING, "gold"),
            ("country", STRING, "IE"),
            ("bookings", INTEGER, 6),
        ],
    },
]

TRAIT_KEYS = {STRING: "string_value", INTEGER: "integer_value", BOOLEAN: "boolean_value"}


def seed():
    project = Project.objects.get(name=PROJECT_NAME)
    environments = {
        env.name: env for env in project.environments.filter(
            name__in=["Development", "Production"]
        )
    }
    assert set(environments) == {"Development", "Production"}, environments

    tags = {
        label: Tag.objects.create(project=project, label=label, color=color)
        for label, color in TAGS
    }

    for spec in FEATURES:
        feature = Feature.objects.create(
            name=spec["name"],
            project=project,
            description=spec["description"],
        )
        feature.tags.set([tags[label] for label in spec["tags"]])
        for env_name, (enabled, value_type, value) in spec["states"].items():
            state = feature.feature_states.get(
                environment=environments[env_name], identity=None, feature_segment=None
            )
            state.enabled = enabled
            state.live_from = spec["created"]
            state.save()
            state.feature_state_value.set_value(value, value_type)
            state.feature_state_value.save()
        # Pin creation stamps for the list's Created Date sort and date column.
        Feature.objects.filter(id=feature.id).update(created_date=spec["created"])
        feature.feature_states.all().update(
            created_at=spec["created"], updated_at=spec["created"]
        )

    for spec in SEGMENTS:
        conditions = [
            {
                "property": prop,
                "operator": operator,
                "value": value,
                "description": None,
            }
            for prop, operator, value in spec["conditions"]
        ]
        # The UI renders conditions from the root rule's nested orphan rules:
        # root (ALL) -> child (ALL|ANY|NONE) -> conditions. Conditions placed
        # directly on the root are ignored by the segment editor.
        segment = Segment.objects.create(
            name=spec["name"],
            description=spec["description"],
            project=project,
            rules_data=[
                {
                    "type": SegmentRule.ALL_RULE,
                    "conditions": [],
                    "rules": [
                        {
                            "type": SegmentRule.ALL_RULE,
                            "conditions": conditions,
                            "rules": [],
                        }
                    ],
                }
            ],
        )
        root_rule = SegmentRule.objects.create(
            segment=segment, type=SegmentRule.ALL_RULE
        )
        group_rule = SegmentRule.objects.create(
            rule=root_rule, type=SegmentRule.ALL_RULE
        )
        for prop, operator, value in spec["conditions"]:
            Condition.objects.create(
                rule=group_rule,
                property=prop,
                operator=operator,
                value=value,
                created_with_segment=True,
            )

    development = environments["Development"]
    for spec in IDENTITIES:
        identity = Identity.objects.create(
            identifier=spec["identifier"], environment=development
        )
        Identity.objects.filter(id=identity.id).update(
            created_date=ts("2026-10-05 08:00")
        )
        for key, value_type, value in spec["traits"]:
            Trait.objects.create(
                identity=identity,
                trait_key=key,
                value_type=value_type,
                **{TRAIT_KEYS[value_type]: value},
            )

    print(
        f"seeded {PROJECT_NAME}: {len(FEATURES)} features, {len(TAGS)} tags, "
        f"{len(SEGMENTS)} segments, {len(IDENTITIES)} identities"
    )


seed()
