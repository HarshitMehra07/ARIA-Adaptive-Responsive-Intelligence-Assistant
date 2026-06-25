from screen.activity_engine import (
    ActivityEngine
)

from screen.focus_engine import (
    FocusEngine
)

activity = ActivityEngine.detect()

print(activity)

print(
    FocusEngine.evaluate(
        activity
    )
)