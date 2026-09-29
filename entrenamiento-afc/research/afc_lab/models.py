from __future__ import annotations

try:
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - exercised only without ML extras
    raise ImportError("Install research/requirements-ml.txt to use neural models") from exc


class SpectralMlp(nn.Module):
    def __init__(self, bins: int = 513, hidden: int = 512) -> None:
        super().__init__()
        features = bins * 2
        self.network = nn.Sequential(
            nn.Linear(features, hidden), nn.ReLU(), nn.Linear(hidden, features)
        )

    def forward(self, spectrum):
        return self.network(spectrum)


class CausalSpectralGru(nn.Module):
    def __init__(self, bins: int = 513, hidden: int = 384) -> None:
        super().__init__()
        features = bins * 2
        self.gru = nn.GRU(features, hidden, batch_first=True)
        self.output = nn.Linear(hidden, features)

    def forward(self, spectrum, state=None):
        encoded, state = self.gru(spectrum, state)
        return self.output(encoded), state


class CompactDeepMfc(nn.Module):
    """Compact frequency encoder + recurrent bottleneck + dual complex decoders."""

    def __init__(self, bins: int = 513, base_channels: int = 8, hidden: int = 256) -> None:
        super().__init__()
        channels = [2, base_channels, base_channels * 2, base_channels * 4]
        encoder = []
        for source, target in zip(channels[:-1], channels[1:]):
            encoder += [nn.Conv2d(source, target, (1, 3), stride=(1, 2)), nn.PReLU(target)]
        self.encoder = nn.Sequential(*encoder)
        encoded_bins = bins
        for _ in range(3):
            encoded_bins = (encoded_bins - 3) // 2 + 1
        bottleneck = channels[-1] * encoded_bins
        self.recurrent = nn.GRU(bottleneck, hidden, batch_first=True)
        self.project = nn.Linear(hidden, bottleneck)
        self.real = nn.Linear(bottleneck, bins)
        self.imag = nn.Linear(bottleneck, bins)

    def forward(self, spectrum, state=None):
        # spectrum: [batch, time, bins, real_imag]
        encoded = self.encoder(spectrum.permute(0, 3, 1, 2))
        batch, channels, frames, bins = encoded.shape
        sequence = encoded.permute(0, 2, 1, 3).reshape(batch, frames, channels * bins)
        sequence, state = self.recurrent(sequence, state)
        sequence = self.project(sequence)
        return torch.stack((self.real(sequence), self.imag(sequence)), dim=-1), state


def create_model(name: str, bins: int = 513):
    if name == "mlp":
        return SpectralMlp(bins)
    if name == "gru":
        return CausalSpectralGru(bins)
    if name == "deepmfc":
        return CompactDeepMfc(bins)
    raise ValueError(f"unknown model: {name}")
