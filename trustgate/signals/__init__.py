"""Signals score one dimension of risk for an action request.

Each signal returns a SignalResult with a risk in [0, 1] and a short reason.
Add a signal by implementing the Signal protocol (see base.py) and dropping it
into the TrustScorer's signal list.
"""
