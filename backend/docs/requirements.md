# Requirements (team draft, in progress)

Transcribed from the team PDF "Moon Flyers - Nasa Space Apps Hackathon" (2026-11-14).
The PDF is the source; update this file when it changes. Our notes are in _italics_.

## Feature table
| Requirement | Min implementation | Priority |
|---|---|---|
| Default landing site selection | Pick from 5–6 predefined south-pole sites with known coordinates | Must |
| Add custom coordinates | Add a site: name, latitude, longitude | Must |
| Mission planning | Start and end date with a fixed interval (for example 1 h); days on surface (lunar or Earth days?); horizon clearance; power: min/max Sun and Earth visibility over the time on the surface, in % | Must |
| Sun position | Sun azimuth and elevation at given coordinates and an arbitrary time, in lunar local coordinates | Must |
| Earth position | Earth azimuth and elevation at given coordinates and an arbitrary time, in lunar local coordinates | Must |
| Horizon visualization | Sun and Earth elevations relative to a clearly defined horizon | Must (frontend) |
| Visibility windows | Periods when the Sun and Earth are above the modelled horizon | Must |
| Scenario comparison | Two site/date scenarios, key metrics side by side | Must |
| Results dashboard | Charts and key indicators in an understandable interface | Must (frontend) |
| Terrain-aware horizon | NASA LOLA elevation data for mountains and crater rims blocking the Sun or Earth | Very High (the PDF). _The user deferred it on 2026-11-14 until the Musts work._ |
| Time slider / animation | Sun and Earth movement as time advances | Very High (frontend, uses the time series) |
| Landing-window finder | Auto-find periods meeting user-defined illumination and comms requirements | Nice-to-have |
| Mission duration input | Evaluate conditions over a user-specified surface mission duration | Nice-to-have |
| Mission configuration | Solar-panel orientation, battery capacity, antenna height | Nice-to-have |
| Educational mode | Explain lighting, Earth visibility and geometry to non-technical users | Low |
| Interactive lunar map | 2D/3D south-pole map; click to select a site | Nice-to-have |

## Inputs
| Field | Type | Meaning |
|---|---|---|
| `latitude_deg` | float | Lunar latitude, −90 to +90 |
| `longitude_deg` | float | Lunar longitude, −180 to +180, east-positive |
| `window_start_utc` | string | Start of the calculation interval |
| `window_end_utc` | string | End of the calculation interval |
| `timestep_seconds` | int | Sampling interval |
| `options.sun_visibility` | _bool?_ | Calculate Sun position and visibility |
| `options.earth_visibility` | _bool?_ | Calculate Earth position and visibility |

## Time-series outputs (one entry per `time_utc`)
| Field | Type | Meaning |
|---|---|---|
| `time_utc` | string | UTC timestamp, the key for each entry |
| `sun_azimuth_deg` | float | Sun azimuth from the observer |
| `sun_elevation_deg` | float | Sun elevation from the observer |
| `sun_visible` | bool | Is the solar disc **entirely** above the az/el mask? |
| `earth_azimuth_deg` | float | Earth azimuth from the observer |
| `earth_elevation_deg` | float | Earth elevation from the observer |
| `earth_visible` | bool | Is Earth's disc **entirely** above the az/el mask? |

## Terrain outputs
| Field | Type | Meaning |
|---|---|---|
| `horizon_azimuth_deg` | array | deg |
| `horizon_elevation_deg` | array | deg |
| `slope_deg` | float | _unspecified_ |
| `altitud…` | _incomplete in the PDF_ | |

## Metrics outputs
`sun_visible_pct`, `longest_darkness_hours`, `earth_visible_pct`,
`longest_earth_blackout_hours`, `slope_deg`. _Types and definitions are blank in the PDF._
