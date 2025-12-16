# SiNE Scene Files

This directory contains Mitsuba XML scene files for ray tracing simulations.

## Default Scene: two_room_default.xml

A simple indoor environment with two adjacent rooms connected by a doorway.

### Layout (Top View)

```
Y
^
|  +--------+----+--------+
|  |        |    |        |
4  | Room 1 |door| Room 2 |
|  |        |    |        |
|  |        |    |        |
0  +--------+----+--------+
   0        5  5.15      10.15  -> X
```

### Dimensions

| Element | Value |
|---------|-------|
| Room 1 | 5.0m x 4.0m x 2.5m (x: 0-5, y: 0-4) |
| Room 2 | 5.0m x 4.0m x 2.5m (x: 5.15-10.15, y: 0-4) |
| Wall thickness | 0.15m |
| Door width | 0.9m |
| Door height | 2.0m |
| Door center | y = 2.0m |
| Ceiling height | 2.5m |

### Coordinate System

- **Origin**: Bottom-left corner of Room 1 at floor level
- **X-axis**: Positive toward Room 2 (left to right)
- **Y-axis**: Positive toward front walls (bottom to top in diagram)
- **Z-axis**: Positive upward (floor to ceiling)

### Example Node Positions

| Position | Coordinates (x, y, z) | Description |
|----------|----------------------|-------------|
| Room 1 center | (2.5, 2.0, 1.5) | Middle of Room 1 at typical device height |
| Room 2 center | (7.5, 2.0, 1.0) | Middle of Room 2 at typical device height |
| Near doorway R1 | (4.5, 2.0, 1.0) | Room 1 side near door |
| Near doorway R2 | (5.5, 2.0, 1.0) | Room 2 side near door |

### Materials

- **Walls**: Concrete (diffuse reflectance ~0.5)
- **Floor**: Concrete
- **Ceiling**: Concrete

## Creating Custom Scenes

You can create custom scenes using:

1. **Blender** with the Mitsuba-Blender add-on
2. **OpenStreetMap** data with the sionna_osm_scene project
3. **Manual XML editing** following Mitsuba 3 scene format

### Requirements for SiNE Compatibility

- Mitsuba 3 scene format (version 2.0.0+)
- Right-handed coordinate system with Z-up
- Units in meters
- Shapes should have appropriate radio materials for Sionna

### Loading Custom Scenes

In your `network.yaml`:

```yaml
topology:
  scene:
    type: custom
    file: /path/to/your/scene.xml
```

## References

- [Mitsuba 3 Documentation](https://mitsuba.readthedocs.io/)
- [Sionna RT Documentation](https://nvlabs.github.io/sionna/rt/)
- [Blender](https://www.blender.org/)
