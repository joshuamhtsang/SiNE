"""Integration tests validating Ray Tracing → Netem physical phenomena.

This test suite demonstrates what SiNE captures via Sionna RT and what it does not.
It validates the OFDM-based channel model assumptions and limitations.

Tests verify:
1. Multipath diversity gain for OFDM (incoherent summation)
2. Delay spread within cyclic prefix bounds
3. LOS vs NLOS path loss differences
4. OFDM cyclic prefix prevents ISI/fading at packet level
5. Static channel (no fast fading without mobility)

See dev_resources/PLAN_rt_and_netem.md for detailed design rationale.
"""

import math
from pathlib import Path

import numpy as np
import pytest
import requests

from tests.integration.fixtures import channel_server


# =============================================================================
# Helper Functions
# =============================================================================


def compute_free_space_path_loss(distance_m: float, frequency_hz: float) -> float:
    """Compute free-space path loss (FSPL) using Friis equation.

    Args:
        distance_m: Distance between TX and RX in meters
        frequency_hz: Carrier frequency in Hz

    Returns:
        Path loss in dB

    Formula:
        FSPL(dB) = 20·log10(d) + 20·log10(f) + 20·log10(4π/c)
                 = 20·log10(d) + 20·log10(f) - 147.55
        where d is in meters, f is in Hz, c = 3×10^8 m/s
    """
    c = 3e8  # Speed of light in m/s
    wavelength = c / frequency_hz
    fspl_linear = (4 * math.pi * distance_m / wavelength) ** 2
    fspl_db = 10 * math.log10(fspl_linear)
    return fspl_db


def load_scene_and_compute_channel(
    channel_server_url: str,
    scene_file: str,
    tx_position: list[float],
    rx_position: list[float],
    frequency_ghz: float = 5.18,
    tx_power_dbm: float = 20.0,
    antenna_gain_dbi: float = 2.15,
    bandwidth_mhz: float = 80.0,
) -> dict:
    """Load scene and compute channel conditions.

    Args:
        channel_server_url: Base URL of the channel server
        scene_file: Path to Mitsuba scene XML file
        tx_position: [x, y, z] position of transmitter in meters
        rx_position: [x, y, z] position of receiver in meters
        frequency_ghz: Carrier frequency in GHz
        tx_power_dbm: Transmit power in dBm
        antenna_gain_dbi: Antenna gain in dBi
        bandwidth_mhz: Channel bandwidth in MHz

    Returns:
        Dictionary with channel computation result including:
        - path_loss_db
        - snr_db
        - delay_spread_ns
        - num_paths
        - propagation_paths (list of path details)
    """
    # Load scene with frequency and bandwidth
    load_response = requests.post(
        f"{channel_server_url}/scene/load",
        json={
            "scene_file": scene_file,
            "frequency_hz": frequency_ghz * 1e9,
            "bandwidth_hz": bandwidth_mhz * 1e6,
        },
        timeout=30,
    )
    load_response.raise_for_status()

    # Compute channel
    # Convert list positions to Position dict format (server.py Position model)
    tx_pos_dict = {"x": tx_position[0], "y": tx_position[1], "z": tx_position[2]}
    rx_pos_dict = {"x": rx_position[0], "y": rx_position[1], "z": rx_position[2]}

    compute_response = requests.post(
        f"{channel_server_url}/compute/single",
        json={
            "tx_node": "tx",
            "rx_node": "rx",
            "tx_position": tx_pos_dict,
            "rx_position": rx_pos_dict,
            "frequency_hz": frequency_ghz * 1e9,
            "tx_power_dbm": tx_power_dbm,
            "tx_gain_dbi": antenna_gain_dbi,
            "rx_gain_dbi": antenna_gain_dbi,
            "bandwidth_hz": bandwidth_mhz * 1e6,
        },
        timeout=30,
    )
    compute_response.raise_for_status()

    return compute_response.json()


def get_debug_paths(
    channel_server_url: str,
    scene_file: str,
    tx_position: list[float],
    rx_position: list[float],
    frequency_ghz: float = 5.18,
    bandwidth_mhz: float = 80.0,
) -> dict:
    """Get detailed path information for debugging.

    Args:
        channel_server_url: Base URL of the channel server
        scene_file: Path to Mitsuba scene XML file
        tx_position: [x, y, z] position of transmitter in meters
        rx_position: [x, y, z] position of receiver in meters
        frequency_ghz: Carrier frequency in GHz
        bandwidth_mhz: Channel bandwidth in MHz

    Returns:
        Dictionary with detailed path information including:
        - distance_m: Direct line distance
        - num_paths: Number of valid paths
        - paths: List of path details (delay, power, interactions, vertices)
        - strongest_path: Path with highest power
        - shortest_path: Path with lowest delay
    """
    # Load scene with frequency and bandwidth
    load_response = requests.post(
        f"{channel_server_url}/scene/load",
        json={
            "scene_file": scene_file,
            "frequency_hz": frequency_ghz * 1e9,
            "bandwidth_hz": bandwidth_mhz * 1e6,
        },
        timeout=30,
    )
    load_response.raise_for_status()

    # Get debug paths
    # Convert list positions to Position dict format (server.py Position model)
    tx_pos_dict = {"x": tx_position[0], "y": tx_position[1], "z": tx_position[2]}
    rx_pos_dict = {"x": rx_position[0], "y": rx_position[1], "z": rx_position[2]}

    debug_response = requests.post(
        f"{channel_server_url}/debug/paths",
        json={
            "tx_name": "tx",
            "rx_name": "rx",
            "tx_position": tx_pos_dict,
            "rx_position": rx_pos_dict,
        },
        timeout=30,
    )
    debug_response.raise_for_status()

    return debug_response.json()


# =============================================================================
# Test 1: Multipath Diversity Gain for OFDM
# =============================================================================


def test_multipath_diversity_gain_for_ofdm(channel_server, scenes_dir: Path):
    """Validate that SiNE's incoherent summation correctly models OFDM diversity gain.

    This test demonstrates that multipath propagation HELPS OFDM receivers through
    diversity gain, rather than causing destructive interference. This is the
    CORRECT behavior for WiFi 6/OFDM systems.

    Physical Basis:
    - OFDM receiver performs FFT → per-subcarrier coherent combining
    - Averaging across 234+ subcarriers (80 MHz) → E[|H(f)|²] ≈ Σ|aᵢ|²
    - Cyclic prefix (0.8-3.2 μs) >> delay spread (20-300 ns) prevents ISI
    - Result: Multipath provides diversity gain (0-3 dB typical)

    Setup:
    - Two-room scene with doorway (guaranteed multipath)
    - TX at (0, 0, 1), RX at (3, 4, 1) - ensures LOS + reflections
    - Compare total power (incoherent sum) to strongest single path

    Expected:
    - Multiple paths detected (LOS + reflections)
    - Diversity gain = 10·log10(Σ|aᵢ|²) - 10·log10(max(|aᵢ|²)) > 0
    - Diversity gain in realistic range: 0-3 dB
    - Indoor path loss > FSPL (walls add loss)
    """
    # Setup
    scene_file = str(scenes_dir / "two_rooms.xml")
    tx_pos = [0.0, 0.0, 1.0]
    rx_pos = [3.0, 4.0, 1.0]  # 5m distance
    frequency_ghz = 5.18
    frequency_hz = frequency_ghz * 1e9

    # Compute direct distance
    distance_m = math.sqrt(
        (rx_pos[0] - tx_pos[0])**2 +
        (rx_pos[1] - tx_pos[1])**2 +
        (rx_pos[2] - tx_pos[2])**2
    )

    # Compute free-space baseline
    fspl_db = compute_free_space_path_loss(distance_m, frequency_hz)

    # Get channel result from Sionna RT
    result = load_scene_and_compute_channel(
        channel_server_url=channel_server,
        scene_file=scene_file,
        tx_position=tx_pos,
        rx_position=rx_pos,
        frequency_ghz=frequency_ghz,
    )

    # Get detailed path info
    paths_info = get_debug_paths(
        channel_server_url=channel_server,
        scene_file=scene_file,
        tx_position=tx_pos,
        rx_position=rx_pos,
        frequency_ghz=frequency_ghz,
    )

    # Validate multipath exists
    num_paths = paths_info["num_paths"]
    assert num_paths >= 2, (
        f"Expected multiple paths in two-room scene, got {num_paths}. "
        "Multipath is required for this test."
    )

    # Extract path powers and compute diversity gain correctly
    # Diversity gain = benefit of using all paths vs only the strongest path
    path_powers_db = [p["power_db"] for p in paths_info["paths"]]
    strongest_path_db = max(path_powers_db)

    # Total path loss from incoherent sum (already computed by SiNE)
    path_loss_db = result["path_loss_db"]

    # Compute diversity gain: how much better is using all paths vs strongest path?
    # Path gain (dB) = -Path loss (dB)
    total_path_gain_db = -path_loss_db
    strongest_path_gain_db = strongest_path_db
    diversity_gain_db = total_path_gain_db - strongest_path_gain_db

    # Print diagnostic info
    print(f"\n{'='*70}")
    print("Test 1: Multipath Diversity Gain for OFDM")
    print(f"{'='*70}")
    print(f"Distance: {distance_m:.2f} m")
    print(f"Frequency: {frequency_ghz} GHz")
    print(f"Number of paths: {num_paths}")
    print(f"Free-space path loss (FSPL): {fspl_db:.2f} dB")
    print(f"Actual path loss (indoor): {path_loss_db:.2f} dB")
    print(f"Excess loss (indoor vs free-space): {path_loss_db - fspl_db:.2f} dB")
    print(f"\nStrongest path gain: {strongest_path_gain_db:.2f} dB")
    print(f"Total path gain (incoherent sum): {total_path_gain_db:.2f} dB")
    print(f"Diversity gain: {diversity_gain_db:.2f} dB")
    print(f"{'='*70}\n")

    # Validate physics: indoor path loss > FSPL (walls add loss)
    assert path_loss_db > fspl_db, (
        f"Expected indoor path loss ({path_loss_db:.2f} dB) > FSPL ({fspl_db:.2f} dB). "
        "Indoor scenes with walls should have higher loss than free-space."
    )

    # Validate OFDM diversity gain behavior
    assert diversity_gain_db >= 0, (
        f"Expected diversity gain ≥ 0 dB for OFDM, got {diversity_gain_db:.2f} dB. "
        "Using all paths should provide gain over using only the strongest path."
    )

    assert diversity_gain_db <= 3.5, (
        f"Expected diversity gain ≤ 3.5 dB (realistic OFDM range), got {diversity_gain_db:.2f} dB. "
        "Excessive diversity gain may indicate incorrect channel model."
    )


# =============================================================================
# Test 2: Delay Spread Within Cyclic Prefix
# =============================================================================


def test_delay_spread_within_cyclic_prefix(channel_server, scenes_dir: Path):
    """Verify that delay spread remains within WiFi 6 cyclic prefix bounds.

    This test validates the OFDM operating assumptions are met. For OFDM to
    work correctly without ISI, the RMS delay spread must be smaller than
    the cyclic prefix duration.

    WiFi 6 Cyclic Prefix:
    - Short GI: 0.8 μs = 800 ns
    - Normal GI: 1.6 μs = 1600 ns
    - Long GI: 3.2 μs = 3200 ns

    Typical Indoor Delay Spread:
    - Free-space/LOS: < 10 ns
    - Indoor with multipath: 20-300 ns
    - Dense urban: 300-800 ns

    Setup:
    - Scenario A: Free-space (vacuum.xml), 20m → minimal delay spread
    - Scenario B: Two-room scene, moderate distance → moderate delay spread

    Expected:
    - Scenario A: delay_spread_ns < 10 ns (nearly zero for LOS)
    - Scenario B: 0 < delay_spread_ns < 800 ns (within short GI CP)
    - Coherence bandwidth > subcarrier spacing (frequency-flat per subcarrier)
    """
    frequency_ghz = 5.18
    subcarrier_spacing_mhz = 80.0 / 234.0  # WiFi 6: 80 MHz / 234 subcarriers ≈ 0.342 MHz

    # Scenario A: Free-space
    print(f"\n{'='*70}")
    print("Test 2a: Delay Spread - Free Space")
    print(f"{'='*70}")

    result_a = load_scene_and_compute_channel(
        channel_server_url=channel_server,
        scene_file=str(scenes_dir / "vacuum.xml"),
        tx_position=[0.0, 0.0, 1.0],
        rx_position=[20.0, 0.0, 1.0],
        frequency_ghz=frequency_ghz,
    )

    delay_spread_a = result_a["delay_spread_ns"]
    print(f"Delay spread (free-space): {delay_spread_a:.3f} ns")

    assert delay_spread_a < 10, (
        f"Expected delay_spread < 10 ns for free-space LOS, got {delay_spread_a:.3f} ns"
    )

    # Scenario B: Two-room indoor
    print(f"\n{'='*70}")
    print("Test 2b: Delay Spread - Indoor Multipath")
    print(f"{'='*70}")

    result_b = load_scene_and_compute_channel(
        channel_server_url=channel_server,
        scene_file=str(scenes_dir / "two_rooms.xml"),
        tx_position=[0.0, 0.0, 1.0],
        rx_position=[3.0, 4.0, 1.0],
        frequency_ghz=frequency_ghz,
    )

    delay_spread_b = result_b["delay_spread_ns"]
    print(f"Delay spread (indoor): {delay_spread_b:.3f} ns")

    assert delay_spread_b > 0, (
        f"Expected delay_spread > 0 ns with multipath, got {delay_spread_b:.3f} ns"
    )

    assert delay_spread_b < 800, (
        f"Expected delay_spread < 800 ns (WiFi 6 short GI CP), got {delay_spread_b:.3f} ns. "
        "Delay spread exceeds cyclic prefix - OFDM assumptions may be violated!"
    )

    # Verify coherence bandwidth > subcarrier spacing
    if delay_spread_b > 0:
        coherence_bw_mhz = 1000.0 / (2 * np.pi * delay_spread_b)
        print(f"Coherence bandwidth: {coherence_bw_mhz:.2f} MHz")
        print(f"Subcarrier spacing: {subcarrier_spacing_mhz:.3f} MHz")

        assert coherence_bw_mhz > subcarrier_spacing_mhz, (
            f"Coherence BW ({coherence_bw_mhz:.2f} MHz) < subcarrier spacing "
            f"({subcarrier_spacing_mhz:.3f} MHz). Channel is frequency-selective "
            "within a subcarrier - OFDM flat-fading assumption violated!"
        )

    print(f"{'='*70}\n")


# =============================================================================
# Test 3: LOS vs NLOS Loss Difference
# =============================================================================


def test_los_vs_nlos_loss_difference(channel_server, scenes_dir: Path):
    """Demonstrate LOS vs NLOS path loss difference captured by ray tracing.

    Ray tracing accounts for:
    - Direct line-of-sight propagation (LOS)
    - Wall penetration loss (NLOS)
    - Diffraction and reflections

    Setup:
    - LOS: Free-space (vacuum.xml), 10m distance
    - NLOS: Two-room scene, 10m distance through wall at x=20m
            TX at [15, 20, 0.5], RX at [25, 20, 0.5]
            (z=0.5m is in the bottom wall section, ensuring wall blockage)

    Expected:
    - LOS: Lower path_loss_db, higher SNR
    - NLOS: Higher path_loss_db (wall adds 10+ dB loss), lower SNR
    """
    frequency_ghz = 5.18
    distance_m = 10.0

    # LOS scenario: Free-space at 10m
    print(f"\n{'='*70}")
    print("Test 3a: LOS Path Loss")
    print(f"{'='*70}")

    result_los = load_scene_and_compute_channel(
        channel_server_url=channel_server,
        scene_file=str(scenes_dir / "vacuum.xml"),
        tx_position=[0.0, 0.0, 1.0],
        rx_position=[distance_m, 0.0, 1.0],
        frequency_ghz=frequency_ghz,
    )

    los_path_loss = result_los["path_loss_db"]
    los_snr = result_los["snr_db"]

    print(f"LOS Path Loss: {los_path_loss:.2f} dB")
    print(f"LOS SNR: {los_snr:.2f} dB")
    print(f"LOS Distance: {distance_m:.2f} m")

    # NLOS scenario: Two-room with wall blocking at same 10m distance
    # Wall is at x=20m, so TX at x=15m and RX at x=25m gives 10m separation
    # Use z=0.5m to be in the bottom wall section (z=0-1m) which has no doorway
    print(f"\n{'='*70}")
    print("Test 3b: NLOS Path Loss (Wall Blocking)")
    print(f"{'='*70}")

    tx_nlos = [15.0, 20.0, 0.5]
    rx_nlos = [25.0, 20.0, 0.5]
    nlos_distance = math.sqrt(sum((rx_nlos[i] - tx_nlos[i])**2 for i in range(3)))

    result_nlos = load_scene_and_compute_channel(
        channel_server_url=channel_server,
        scene_file=str(scenes_dir / "two_rooms.xml"),
        tx_position=tx_nlos,
        rx_position=rx_nlos,
        frequency_ghz=frequency_ghz,
    )

    nlos_path_loss = result_nlos["path_loss_db"]
    nlos_snr = result_nlos["snr_db"]

    print(f"NLOS Path Loss: {nlos_path_loss:.2f} dB")
    print(f"NLOS SNR: {nlos_snr:.2f} dB")
    print(f"NLOS Distance: {nlos_distance:.2f} m")

    # Compute additional loss from NLOS
    additional_loss = nlos_path_loss - los_path_loss

    print(f"\nAdditional NLOS loss: {additional_loss:.2f} dB")
    print(f"{'='*70}\n")

    # Validate distances are the same (within 0.1m tolerance)
    assert abs(nlos_distance - distance_m) < 0.1, (
        f"Test setup error: distances should be equal. "
        f"LOS={distance_m:.2f}m, NLOS={nlos_distance:.2f}m"
    )

    # Validate NLOS has higher path loss
    assert nlos_path_loss > los_path_loss, (
        f"Expected NLOS path loss ({nlos_path_loss:.2f} dB) > LOS path loss "
        f"({los_path_loss:.2f} dB). Wall should add significant loss."
    )

    # Wall penetration loss should be significant (typically 10+ dB for concrete)
    assert additional_loss >= 5.0, (
        f"Expected wall to add ≥5 dB loss, got {additional_loss:.2f} dB. "
        "NLOS propagation should have significant attenuation."
    )

    # NLOS should have lower SNR
    assert nlos_snr < los_snr, (
        f"Expected NLOS SNR ({nlos_snr:.2f} dB) < LOS SNR ({los_snr:.2f} dB)"
    )


# =============================================================================
# Test 4: OFDM Cyclic Prefix Prevents ISI/Fading
# =============================================================================


def test_ofdm_cyclic_prefix_prevents_isi_fading(channel_server, scenes_dir: Path):
    """Demonstrate OFDM's resilience to multipath fading at packet level.

    For narrowband single-carrier systems, multipath with certain phase
    relationships can cause deep fades (destructive interference). However,
    OFDM with cyclic prefix prevents this at the packet level through:

    1. Per-subcarrier coherent combining: H(f) = Σ aᵢ·e^(-j2πfτᵢ) for each subcarrier
    2. Frequency diversity: Averaging across 234+ subcarriers
    3. Cyclic prefix: Prevents ISI and allows perfect equalization per subcarrier

    Result: Multipath provides diversity gain, not deep fades.

    Setup:
    - Position TX/RX to create multiple paths with varying phase relationships
    - Two-room scene ensures multipath with reflections
    - Phase relationships vary based on path delays

    Expected (correct OFDM behavior):
    - Phase relationships vary between paths (computed from delay difference)
    - Diversity gain = total power vs strongest path > 0 dB
    - Diversity gain bounded: 0-3 dB typical
    - Indoor path loss > FSPL (walls add loss)
    """
    frequency_ghz = 5.18
    frequency_hz = frequency_ghz * 1e9
    wavelength_m = 3e8 / frequency_hz  # ~0.058 m at 5.18 GHz

    # Test with two-room scene (multipath)
    print(f"\n{'='*70}")
    print("Test 4: OFDM Cyclic Prefix Prevents ISI/Fading")
    print(f"{'='*70}")

    scene_file = str(scenes_dir / "two_rooms.xml")
    tx_pos = [0.0, 0.0, 1.0]
    rx_pos = [3.0, 4.0, 1.0]

    # Get detailed path info
    paths_info = get_debug_paths(
        channel_server_url=channel_server,
        scene_file=scene_file,
        tx_position=tx_pos,
        rx_position=rx_pos,
        frequency_ghz=frequency_ghz,
    )

    # Get channel result
    result = load_scene_and_compute_channel(
        channel_server_url=channel_server,
        scene_file=scene_file,
        tx_position=tx_pos,
        rx_position=rx_pos,
        frequency_ghz=frequency_ghz,
    )

    # Compute direct distance for free-space baseline
    distance_m = paths_info["distance_m"]
    fspl_db = compute_free_space_path_loss(distance_m, frequency_hz)

    # Extract path delays
    num_paths = paths_info["num_paths"]
    assert num_paths >= 2, "Need multiple paths for this test"

    path_delays = [p["delay_ns"] for p in paths_info["paths"]]
    min_delay = min(path_delays)
    max_delay = max(path_delays)
    delta_tau_ns = max_delay - min_delay

    # Calculate phase difference for reference (informational only)
    # At carrier frequency, phase difference between paths
    phase_diff_deg = (delta_tau_ns * 1e-9 * frequency_hz * 360) % 360

    # Compute diversity gain correctly: all paths vs strongest path
    path_powers_db = [p["power_db"] for p in paths_info["paths"]]
    strongest_path_db = max(path_powers_db)
    path_loss_db = result["path_loss_db"]

    total_path_gain_db = -path_loss_db
    strongest_path_gain_db = strongest_path_db
    diversity_gain_db = total_path_gain_db - strongest_path_gain_db

    print(f"Number of paths: {num_paths}")
    print(f"Path delay range: {min_delay:.2f} - {max_delay:.2f} ns")
    print(f"Delay difference: {delta_tau_ns:.2f} ns")
    print(f"Phase difference (at carrier): {phase_diff_deg:.1f}°")
    print(f"Wavelength: {wavelength_m*1000:.2f} mm")
    print(f"\nFree-space path loss (FSPL): {fspl_db:.2f} dB")
    print(f"Actual path loss (indoor): {path_loss_db:.2f} dB")
    print(f"Excess loss (indoor vs free-space): {path_loss_db - fspl_db:.2f} dB")
    print(f"\nStrongest path gain: {strongest_path_gain_db:.2f} dB")
    print(f"Total path gain (incoherent sum): {total_path_gain_db:.2f} dB")
    print(f"Diversity gain: {diversity_gain_db:.2f} dB")
    print(f"{'='*70}\n")

    # Validate physics: indoor path loss > FSPL
    assert path_loss_db > fspl_db, (
        f"Expected indoor path loss ({path_loss_db:.2f} dB) > FSPL ({fspl_db:.2f} dB). "
        "Indoor scenes with walls should have higher loss than free-space."
    )

    # Validate OFDM behavior: multipath provides diversity gain, not fading nulls
    assert diversity_gain_db >= 0, (
        f"Expected diversity gain ≥ 0 dB for OFDM, got {diversity_gain_db:.2f} dB. "
        "OFDM with cyclic prefix should benefit from multipath through frequency diversity."
    )

    assert diversity_gain_db <= 3.5, (
        f"Expected diversity gain ≤ 3.5 dB (realistic OFDM range), got {diversity_gain_db:.2f} dB"
    )


# =============================================================================
# Test 5: Static Channel (No Fast Fading)
# =============================================================================


def test_static_channel_no_fast_fading(channel_server, scenes_dir: Path):
    """Demonstrate that repeated channel computations give identical results.

    SiNE uses deterministic ray tracing, which produces a static channel
    impulse response for fixed TX/RX positions. There is NO time-varying
    fading (Rayleigh/Rician) unless you add stochastic perturbations.

    Setup:
    - Compute channel for same TX/RX position 10 times
    - No mobility, no scene changes

    Expected:
    - All 10 computations return identical netem params
    - Variance in loss_percent ≈ 0
    """
    print(f"\n{'='*70}")
    print("Test 5: Static Channel (No Fast Fading)")
    print(f"{'='*70}")

    scene_file = str(scenes_dir / "two_rooms.xml")
    tx_pos = [0.0, 0.0, 1.0]
    rx_pos = [3.0, 4.0, 1.0]
    frequency_ghz = 5.18

    # Compute channel 10 times
    num_iterations = 10
    results = []

    for _ in range(num_iterations):
        result = load_scene_and_compute_channel(
            channel_server_url=channel_server,
            scene_file=scene_file,
            tx_position=tx_pos,
            rx_position=rx_pos,
            frequency_ghz=frequency_ghz,
        )
        results.append(result)

    # Extract key metrics
    path_losses = [r["path_loss_db"] for r in results]
    snrs = [r["snr_db"] for r in results]
    delay_spreads = [r["delay_spread_ns"] for r in results]

    # Compute statistics
    path_loss_std = np.std(path_losses)
    snr_std = np.std(snrs)
    delay_spread_std = np.std(delay_spreads)

    print(f"Iterations: {num_iterations}")
    print("\nPath Loss:")
    print(f"  Mean: {np.mean(path_losses):.6f} dB")
    print(f"  Std:  {path_loss_std:.6e} dB")
    print("\nSNR:")
    print(f"  Mean: {np.mean(snrs):.6f} dB")
    print(f"  Std:  {snr_std:.6e} dB")
    print("\nDelay Spread:")
    print(f"  Mean: {np.mean(delay_spreads):.6f} ns")
    print(f"  Std:  {delay_spread_std:.6e} ns")
    print(f"{'='*70}\n")

    # Validate static channel (numerically zero variance)
    assert path_loss_std < 1e-6, (
        f"Expected path loss variance ≈ 0 (static channel), got std={path_loss_std:.6e} dB. "
        "Repeated computations should be identical for deterministic ray tracing."
    )

    assert snr_std < 1e-6, (
        f"Expected SNR variance ≈ 0 (static channel), got std={snr_std:.6e} dB"
    )

    assert delay_spread_std < 1e-6, (
        f"Expected delay spread variance ≈ 0 (static channel), got std={delay_spread_std:.6e} ns"
    )

    print("✓ Channel is static - no fast fading without mobility")
    print("  (Time-varying fading requires stochastic modeling on top of deterministic RT)")
