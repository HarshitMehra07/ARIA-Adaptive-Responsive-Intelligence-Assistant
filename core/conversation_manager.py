import time


class ConversationManager:
    """Keep bounded, expiring short-term context isolated per conversation owner."""

    MAX_HISTORY = 20
    MAX_AGE_SECONDS = 6 * 60 * 60
    MAX_SUMMARY_LENGTH = 500
    PRIMARY_USER_ID = "primary_user"

    history = []
    _history_timestamps = []
    current_topic = None
    current_goal = None
    _summary = ""
    _sessions = {}

    @classmethod
    def _is_primary(cls, session_id=None):
        return session_id in (None, "", cls.PRIMARY_USER_ID)

    @classmethod
    def _session(cls, session_id):
        if cls._is_primary(session_id):
            return None
        key = str(session_id)
        return cls._sessions.setdefault(
            key,
            {
                "history": [],
                "timestamps": [],
                "topic": None,
                "goal": None,
                "summary": "",
            },
        )

    @classmethod
    def _summarize_removed(cls, removed, session_id=None):
        snippets = [
            str(turn.get("content", "")).strip().replace("\n", " ")[:120]
            for turn, _timestamp in removed
            if turn.get("role") == "user" and str(turn.get("content", "")).strip()
        ]
        if not snippets:
            return
        state = cls._session(session_id)
        previous = cls._summary if state is None else state["summary"]
        unique = list(dict.fromkeys((previous, *snippets)))
        summary = "Earlier topics: " + " | ".join(item for item in unique if item)
        summary = summary[-cls.MAX_SUMMARY_LENGTH :]
        if state is None:
            cls._summary = summary
        else:
            state["summary"] = summary

    @classmethod
    def _trim_history(cls, session_id=None):
        state = cls._session(session_id)
        history = cls.history if state is None else state["history"]
        timestamps = cls._history_timestamps if state is None else state["timestamps"]
        now = time.time()
        if len(timestamps) < len(history):
            timestamps[:0] = [now] * (len(history) - len(timestamps))
        elif len(timestamps) > len(history):
            del timestamps[: len(timestamps) - len(history)]

        paired = list(zip(history, timestamps))
        retained = [
            (turn, timestamp)
            for turn, timestamp in paired
            if now - timestamp <= cls.MAX_AGE_SECONDS
        ]
        if len(retained) > cls.MAX_HISTORY:
            retained = retained[-cls.MAX_HISTORY :]
        if len(retained) != len(paired):
            retained_ids = {id(turn) for turn, _timestamp in retained}
            removed = [
                pair for pair in paired if id(pair[0]) not in retained_ids
            ]
            cls._summarize_removed(removed, session_id)
            history[:] = [turn for turn, _timestamp in retained]
            timestamps[:] = [timestamp for _turn, timestamp in retained]
            if not retained:
                if state is None:
                    cls.current_topic = None
                    cls.current_goal = None
                else:
                    state["topic"] = None
                    state["goal"] = None

    @classmethod
    def add_user_message(cls, text, session_id=None):
        state = cls._session(session_id)
        history = cls.history if state is None else state["history"]
        timestamps = cls._history_timestamps if state is None else state["timestamps"]
        history.append({"role": "user", "content": text})
        timestamps.append(time.time())
        cls._trim_history(session_id)

    @classmethod
    def add_assistant_message(cls, text, session_id=None):
        state = cls._session(session_id)
        history = cls.history if state is None else state["history"]
        timestamps = cls._history_timestamps if state is None else state["timestamps"]
        history.append({"role": "assistant", "content": text})
        timestamps.append(time.time())
        cls._trim_history(session_id)

    @classmethod
    def set_topic(cls, topic, session_id=None):
        state = cls._session(session_id)
        if state is None:
            cls.current_topic = topic
        else:
            state["topic"] = topic

    @classmethod
    def get_topic(cls, session_id=None):
        cls._trim_history(session_id)
        state = cls._session(session_id)
        return cls.current_topic if state is None else state["topic"]

    @classmethod
    def set_goal(cls, goal, session_id=None):
        state = cls._session(session_id)
        if state is None:
            cls.current_goal = goal
        else:
            state["goal"] = goal

    @classmethod
    def get_goal(cls, session_id=None):
        cls._trim_history(session_id)
        state = cls._session(session_id)
        return cls.current_goal if state is None else state["goal"]

    @classmethod
    def get_history(cls, session_id=None):
        cls._trim_history(session_id)
        state = cls._session(session_id)
        history = cls.history if state is None else state["history"]
        return [turn.copy() for turn in history]

    @classmethod
    def get_summary(cls, session_id=None):
        cls._trim_history(session_id)
        state = cls._session(session_id)
        return cls._summary if state is None else state["summary"]

    @classmethod
    def clear(cls, session_id=None):
        if session_id is None:
            cls.history.clear()
            cls._history_timestamps.clear()
            cls.current_topic = None
            cls.current_goal = None
            cls._summary = ""
            cls._sessions.clear()
            return
        state = cls._session(session_id)
        if state is None:
            cls.history.clear()
            cls._history_timestamps.clear()
            cls.current_topic = None
            cls.current_goal = None
            cls._summary = ""
            return
        state["history"].clear()
        state["timestamps"].clear()
        state["topic"] = None
        state["goal"] = None
        state["summary"] = ""
