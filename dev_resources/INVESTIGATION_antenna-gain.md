# Investigation: Antenna Pattern When Only `antenna_gain_dbi` is Specified

**Date**: 2026-01-29
**Question**: When network.yaml only specifies `antenna_gain_dbi` (without `antenna_pattern`), what antenna pattern does the Sionna engine use?
**Expected**: "iso" with corresponding antenna gain.

## Investigation Summary

### Configuration Flow

**1. Schema Validation** ([src/sine/config/schema.py:266-288](src/sine/config/schema.py#L266-L288))
```python
antenna_pattern: AntennaPattern | None = Field(default=None, ...)
antenna_gain_dbi: float | None = Field(default=None, ...)

@model_validator(mode="after")
def validate_antenna_config(self) -> "WirelessParams":
    """Ensure exactly one of antenna_pattern or antenna_gain_dbi is specified."""
    # Enforces mutual exclusion
```

When YAML specifies only `antenna_gain_dbi: 3.0`:
- ✅ `antenna_pattern = None`
- ✅ `antenna_gain_dbi = 3.0`

**2. Request Building** ([src/sine/emulation/controller.py:319-321](src/sine/emulation/controller.py#L319-L321))
```python
request = {
    "tx_gain_dbi": tx_params.antenna_gain_dbi,  # 3.0
    "rx_gain_dbi": rx_params.antenna_gain_dbi,  # 3.0
    "antenna_pattern": tx_params.antenna_pattern,  # None
    ...
}
```

**3. API Request Model** ([src/sine/channel/server.py:124-126](src/sine/channel/server.py#L124-L126))
```python
class WirelessLinkRequest(BaseModel):
    tx_gain_dbi: float = Field(default=0.0, ...)
    rx_gain_dbi: float = Field(default=0.0, ...)
    antenna_pattern: str = Field(default="iso", ...)  # ← KEY DEFAULT
```

When `antenna_pattern: None` is passed in the request dict:
- Pydantic uses the default value: **`"iso"`**

**4. Sionna Engine Call** ([src/sine/channel/sionna_engine.py:163-169](src/sine/channel/sionna_engine.py#L163-L169))
```python
def add_transmitter(
    self,
    antenna_pattern: str = "iso",  # Default also here
    ...
):
    tx_array = PlanarArray(
        pattern=antenna_pattern,  # "iso" when antenna_gain_dbi is used
        ...
    )
```

**5. SNR Calculation** ([src/sine/channel/server.py:655-661](src/sine/channel/server.py#L655-L661))
```python
signal_power_dbm, snr_db = snr_calc.calculate_link_snr(
    tx_power_dbm=link.tx_power_dbm,
    tx_gain_dbi=link.tx_gain_dbi,  # 3.0 (explicit)
    rx_gain_dbi=link.rx_gain_dbi,  # 3.0 (explicit)
    path_loss_db=path_result.path_loss_db,  # From Sionna with "iso" pattern
    from_sionna=True,
)
```

## Answer: YES, Expectation is Correct ✅

When `network.yaml` specifies only `antenna_gain_dbi`:
1. **Sionna engine uses `"iso"` antenna pattern** (0.0 dBi gain embedded in path coefficients)
2. **SNR calculation uses the explicit `antenna_gain_dbi` value** (e.g., 3.0 dBi)
3. **No double-counting** because iso pattern has 0.0 dBi gain

## Design Rationale

### Two Configuration Modes

**Mode 1: Sionna RT Pattern** (`antenna_pattern` specified)
```yaml
wireless:
  antenna_pattern: hw_dipole  # 2.16 dBi gain
```
- Sionna: Uses `hw_dipole` pattern → path loss includes 2.16 dBi gain
- SNR calc: Uses `tx_gain_dbi=0.0` (default) → no double-counting

**Mode 2: Explicit Gain** (`antenna_gain_dbi` specified)
```yaml
wireless:
  antenna_gain_dbi: 3.0  # Custom antenna
```
- Sionna: Uses `iso` pattern (default) → path loss has 0.0 dBi from pattern
- SNR calc: Uses `tx_gain_dbi=3.0` → explicit gain added in link budget

### Why This Works

The link budget calculation is:
```
SNR (dB) = TX_power + TX_gain + RX_gain - Path_loss - Noise_floor
```

**With antenna_pattern:**
- `Path_loss` from Sionna includes pattern gain (e.g., hw_dipole: 2.16 dBi)
- `TX_gain` and `RX_gain` default to 0.0 dBi
- Result: Pattern gain counted once ✅

**With antenna_gain_dbi:**
- `Path_loss` from Sionna uses iso pattern (0.0 dBi)
- `TX_gain` and `RX_gain` use explicit values (e.g., 3.0 dBi)
- Result: Explicit gain counted once ✅

## Verification Locations

To verify this behavior:

1. **Default values**: Check [src/sine/channel/server.py:126](src/sine/channel/server.py#L126)
   ```python
   antenna_pattern: str = Field(default="iso", ...)
   ```

2. **Sionna engine defaults**: Check [src/sine/channel/sionna_engine.py:167](src/sine/channel/sionna_engine.py#L167)
   ```python
   antenna_pattern: str = "iso"
   ```

3. **SNR calculation**: Check [src/sine/channel/server.py:655-661](src/sine/channel/server.py#L655-L661) uses explicit gains

4. **Antenna pattern gains**: See [src/sine/channel/antenna_patterns.py:26-42](src/sine/channel/antenna_patterns.py#L26-L42)
   - iso: 0.0 dBi
   - dipole: 1.76 dBi
   - hw_dipole: 2.16 dBi
   - tr38901: 8.0 dBi

## Conclusion

The implementation is **correct and matches expectations**:
- When only `antenna_gain_dbi` is specified, Sionna uses the `"iso"` pattern (0.0 dBi)
- The explicit antenna gain is then added during SNR calculation
- This prevents double-counting and allows custom antenna gains outside Sionna's built-in patterns

The mutual exclusion rule in the schema (enforced at [src/sine/config/schema.py:266-288](src/sine/config/schema.py#L266-L288)) ensures users don't accidentally specify both and cause confusion about which value is used.

## Key Files

- **Schema validation**: `src/sine/config/schema.py`
- **Request building**: `src/sine/emulation/controller.py`
- **API models**: `src/sine/channel/server.py`
- **Sionna engine**: `src/sine/channel/sionna_engine.py`
- **Antenna patterns**: `src/sine/channel/antenna_patterns.py`
- **SNR calculation**: `src/sine/channel/snr.py`
