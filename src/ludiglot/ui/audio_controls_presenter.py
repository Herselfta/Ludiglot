from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioControlsViewState:
    enabled: bool
    playing: bool
    progress: float
    duration_ms: int
    time_text: str
    timer_running: bool
    status_message: str | None = None
    update_progress: bool = True


class AudioControlsPresenter:
    def disabled(self, status_message: str | None = None) -> AudioControlsViewState:
        return AudioControlsViewState(
            enabled=False,
            playing=False,
            progress=0.0,
            duration_ms=0,
            time_text="00:00 / 00:00",
            timer_running=False,
            status_message=status_message,
        )

    def ready(self) -> AudioControlsViewState:
        return AudioControlsViewState(
            enabled=True,
            playing=False,
            progress=0.0,
            duration_ms=0,
            time_text="00:00 / 00:00",
            timer_running=False,
        )

    def playing(
        self,
        source_name: str | None,
        progress: float = 0.0,
        duration_ms: int = 0,
    ) -> AudioControlsViewState:
        status = f"正在播放: {source_name}" if source_name else "正在播放"
        return AudioControlsViewState(
            enabled=True,
            playing=True,
            progress=self._clamp_progress(progress),
            duration_ms=max(0, int(duration_ms)),
            time_text=self._time_text(progress, duration_ms),
            timer_running=True,
            status_message=status,
        )

    def paused(self, progress: float, duration_ms: int) -> AudioControlsViewState:
        return AudioControlsViewState(
            enabled=True,
            playing=False,
            progress=self._clamp_progress(progress),
            duration_ms=max(0, int(duration_ms)),
            time_text=self._time_text(progress, duration_ms),
            timer_running=False,
            status_message="已暂停",
        )

    def seeked(self, position: float, duration_ms: int) -> AudioControlsViewState:
        return AudioControlsViewState(
            enabled=True,
            playing=False,
            progress=self._clamp_progress(position),
            duration_ms=max(0, int(duration_ms)),
            time_text=self._time_text(position, duration_ms),
            timer_running=False,
        )

    def progress(self, position: float, duration_ms: int) -> AudioControlsViewState:
        return AudioControlsViewState(
            enabled=True,
            playing=True,
            progress=self._clamp_progress(position),
            duration_ms=max(0, int(duration_ms)),
            time_text=self._time_text(position, duration_ms),
            timer_running=True,
        )

    def ended(self, duration_ms: int) -> AudioControlsViewState:
        return AudioControlsViewState(
            enabled=True,
            playing=False,
            progress=1.0,
            duration_ms=max(0, int(duration_ms)),
            time_text=self._time_text(1.0, duration_ms),
            timer_running=False,
            status_message="播放已结束",
        )

    def _time_text(self, progress: float, duration_ms: int) -> str:
        duration_ms = max(0, int(duration_ms))
        if duration_ms <= 0:
            return "00:00 / 00:00"
        current_ms = int(self._clamp_progress(progress) * duration_ms)
        return f"{self._format_ms(current_ms)} / {self._format_ms(duration_ms)}"

    def _format_ms(self, milliseconds: int) -> str:
        seconds = max(0, int(milliseconds)) // 1000
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _clamp_progress(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
