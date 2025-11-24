"""Minimal stats stub to satisfy optional imports used by the photo frame.
This is intentionally small and non-invasive — it returns None for CPU
temperature and provides a `sensors` namespace similar to the original project.
Add real sensor implementations later if needed by your hardware.
"""

class _Cpu:
    @staticmethod
    def temperature():
        # Return None when no sensor is available
        return None

class _Sensors:
    Cpu = _Cpu

sensors = _Sensors()

# Exported API: sensors
__all__ = ["sensors"]
