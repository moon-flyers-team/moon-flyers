"""Save a rover route, terrain/slope maps and an elevation profile as a PNG.

Run from the repository root; use --demo without LOLA files. Real mode requires
--dem-dir (or LOLA_DEM_DIR). No GUI, API, network or frontend server is needed.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

# Permit `python backend/tools/plot_rover_path.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.Functions.rover_path import MOON_RADIUS_M, plan_rover_route  # noqa: E402


REAL_START = (-89.90461690407035, 0.0)
REAL_GOAL = (-89.90461462373575, -0.3961843417649203)
DEMO_START = (-89.9, 0.0)
DEMO_GOAL = (-89.88, 0.0)


def local_coordinates(lat, lon, origin):
    """North-up spherical azimuthal-equidistant coordinates, in lunar metres."""
    lat, lon = np.radians(lat), np.radians(lon)
    units = np.stack((np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)), axis=-1)
    p, lam = map(math.radians, origin)
    centre = np.array([math.cos(p)*math.cos(lam), math.cos(p)*math.sin(lam), math.sin(p)])
    east = np.array([-math.sin(lam), math.cos(lam), 0])
    north = np.cross(centre, east)
    sine = np.linalg.norm(np.cross(centre, units), axis=-1)
    angle = np.arctan2(sine, units @ centre)
    scale = np.divide(MOON_RADIUS_M*angle, sine, out=np.full_like(angle, MOON_RADIUS_M), where=sine > 0)
    return (units @ east)*scale, (units @ north)*scale


class DemoDEM:
    """Artificial hill that forces a detour; not lunar observations."""
    def sample(self, lat, lon):
        east, north = local_coordinates(lat, lon, DEMO_START)
        return 100 + 60*np.exp(-((north-300)/90)**2-(east/120)**2)


class RecordedDEM:
    """Keep the exact sampled grid so the plot shows the terrain the search used."""
    def __init__(self, dem):
        self.dem = dem
        self.lat = self.lon = self.heights = None

    def sample(self, lat, lon):
        heights = self.dem.sample(lat, lon)
        self.lat, self.lon, self.heights = np.array(lat), np.array(lon), np.array(heights)
        return heights


def cell_edges(centres):
    """Explicit quadrilateral edges for a rotated/curved sampled grid."""
    extended = np.empty((centres.shape[0]+2, centres.shape[1]+2))
    extended[1:-1, 1:-1] = centres
    extended[0, 1:-1] = 2*centres[0]-centres[1]
    extended[-1, 1:-1] = 2*centres[-1]-centres[-2]
    extended[:, 0] = 2*extended[:, 1]-extended[:, 2]
    extended[:, -1] = 2*extended[:, -2]-extended[:, -3]
    return (extended[:-1, :-1]+extended[1:, :-1]+extended[:-1, 1:]+extended[1:, 1:])/4


def plot_route(result, sampled, start, goal, source, output):
    """Render failed routes too, without inventing a line between the endpoints."""
    try:
        # Keep this optional dependency and cache writes out of server startup.
        os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'moon-flyers-matplotlib'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError as exc:
        raise RuntimeError(
            'Install plotting dependencies: python -m pip install -r backend/requirements-visualization.txt'
        ) from exc

    east, north = local_coordinates(sampled.lat, sampled.lon, start)
    gx, gy = local_coordinates(*goal, start)
    # Undo only the grid's rotation to recover its exact metre spacings. The
    # displayed map itself stays north-up, including near the pole/dateline.
    direction = math.atan2(float(gy), float(gx)) if math.hypot(gx, gy) > 1e-8 else 0
    along = east*math.cos(direction)+north*math.sin(direction)
    across = -east*math.sin(direction)+north*math.cos(direction)
    row, col = result['endpoint_checks']['start']['grid_cell']
    height = np.where(np.isfinite(sampled.heights), sampled.heights, np.nan)
    with np.errstate(invalid='ignore', divide='ignore'):
        dy, dx = np.gradient(height, across[:, col], along[row, :])
        slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    limit = result['search']['max_slope_deg']
    unknown = ~np.isfinite(height) | ~np.isfinite(slope)
    steep = ~unknown & (slope > limit+1e-10)

    fig = plt.figure(figsize=(13, 9), layout='constrained')
    layout = fig.add_gridspec(2, 2, height_ratios=[2, 1])
    terrain_ax, slope_ax = fig.add_subplot(layout[0, 0]), fig.add_subplot(layout[0, 1])
    profile_ax = fig.add_subplot(layout[1, :])
    terrain_ax.set_title('Elevation and route')
    slope_ax.set_title(f'Terrain slope — limit {limit:g}°')
    ex, ny = cell_edges(east), cell_edges(north)
    if np.any(np.isfinite(height)):
        mesh = terrain_ax.pcolormesh(ex, ny, np.ma.masked_invalid(height), cmap='terrain', shading='flat')
        fig.colorbar(mesh, ax=terrain_ax, label='Elevation above reference sphere (m)', shrink=.8)
    else:
        terrain_ax.set_title('Elevation unavailable')
    if np.any(np.isfinite(slope)):
        mesh = slope_ax.pcolormesh(ex, ny, np.ma.masked_invalid(slope), cmap='magma', shading='flat',
                                   vmin=0, vmax=max(20, limit*1.5))
        fig.colorbar(mesh, ax=slope_ax, label='Estimated terrain slope (degrees)', shrink=.8, extend='max')
    else:
        slope_ax.set_title('Terrain slope unavailable')
    for ax in (terrain_ax, slope_ax):
        ax.set_facecolor('#d0d0d0')
        # Overlay distinguishes excluded steep cells without changing the colour scale.
        if np.any(steep):
            ax.contourf(east, north, steep.astype(float), levels=[.5, 1.5],
                        colors='none', hatches=['////'])
        if np.any(unknown):
            ax.contourf(east, north, unknown.astype(float), levels=[.5, 1.5], colors=['#888888'])
        ax.plot([0, gx], [0, gy], '--', color='#444444', linewidth=1, label='Direct reference (not a route)')
        ax.scatter([0], [0], s=95, marker='o', facecolors='#39e75f', edgecolors='black', zorder=6, label='Start')
        ax.scatter([gx], [gy], s=110, marker='*', facecolors='#ffdb42', edgecolors='black',
                   zorder=7, label='Destination')
        ax.set_xlabel('East of start (m)')
        ax.set_ylabel('North of start (m)')
        ax.set_aspect('equal')
        ax.grid(alpha=.2)

    if result['status'] == 'route_found':
        path = result['path']
        rx, ry = local_coordinates([p['latitude_deg'] for p in path], [p['longitude_deg'] for p in path], start)
        for ax in (terrain_ax, slope_ax):
            ax.plot(rx, ry, color='#00d9ff', linewidth=3, zorder=5, label='Computed A* route')
        distance = [0.0]
        # Great-circle distances for the profile axis, independent of row/column counts.
        for a, b in zip(path, path[1:]):
            p, q = math.radians(a['latitude_deg']), math.radians(b['latitude_deg'])
            dl = math.radians(b['longitude_deg']-a['longitude_deg'])
            h = math.sin((q-p)/2)**2+math.cos(p)*math.cos(q)*math.sin(dl/2)**2
            distance.append(distance[-1]+2*MOON_RADIUS_M*math.asin(math.sqrt(min(1, max(0, h)))))
        profile_ax.plot(distance, [p['elevation_m'] for p in path], color='#007aa3', marker='.', linewidth=2)
        profile_ax.set_title('Elevation along computed route')
        profile_ax.set_xlabel('Distance along route (m)')
        profile_ax.set_ylabel('Elevation (m)')
        profile_ax.grid(alpha=.25)
        summary = (f"Route {result['distance_m']:.1f} m | Ascent {result['elevation_gain_m']:.1f} m | "
                   f"Maximum modelled slope {result['max_terrain_slope_deg']:.1f}°")
    else:
        summary = result['reason']
        profile_ax.text(.5, .5, f"NO ROUTE DRAWN\n{result['status']}\n{result['reason']}",
                        ha='center', va='center', transform=profile_ax.transAxes, wrap=True)
        profile_ax.set_axis_off()
    handles, labels = terrain_ax.get_legend_handles_labels()
    if np.any(steep):
        handles.append(Patch(facecolor='none', edgecolor='black', hatch='////'))
        labels.append('Terrain slope above limit')
    if np.any(unknown):
        handles.append(Patch(facecolor='#888888'))
        labels.append('Unknown elevation/slope')
    terrain_ax.legend(handles, labels, fontsize=7, loc='best')
    fig.suptitle(f"{source}\n{result['status']} — {summary}", fontsize=12)
    spacing = result['search']['requested_cell_size_m']
    fig.supxlabel(f'{spacing:g} m sampling does not reveal sub-grid hazards. '
                  'Visual inspection is not driving validation.', fontsize=9)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='use a labelled artificial hill; no LOLA files needed')
    parser.add_argument('--dem-dir', default=os.getenv('LOLA_DEM_DIR'), help='real LOLA directory (or LOLA_DEM_DIR)')
    parser.add_argument('--start', type=float, nargs=2, metavar=('LAT', 'LON'))
    parser.add_argument('--goal', type=float, nargs=2, metavar=('LAT', 'LON'))
    parser.add_argument('--cell-size-m', type=float, default=20)
    parser.add_argument('--padding-m', type=float, default=300)
    parser.add_argument('--max-cells', type=int, default=250_000, help='maximum grid cells (memory budget)')
    parser.add_argument('--max-expansions', type=int, default=250_000, help='maximum A* node expansions')
    parser.add_argument('--max-slope-deg', type=float, default=15)
    parser.add_argument('--climb-weight', type=float, default=2)
    parser.add_argument('--slope-weight', type=float, default=1)
    parser.add_argument('--output', type=Path, default=Path('rover_path.png'))
    args = parser.parse_args(argv)
    if args.output.suffix.lower() != '.png':
        parser.error('--output must end in .png (a separate .json report is written beside it)')
    if args.demo:
        if args.start or args.goal:
            parser.error('--demo uses its own coordinates; omit --start and --goal')
        dem, start, goal, source = DemoDEM(), DEMO_START, DEMO_GOAL, 'DEMO — synthetic terrain, not lunar observations'
    else:
        if not args.dem_dir:
            parser.error('provide --dem-dir/LOLA_DEM_DIR for real terrain, or --demo')
        from src.lunar_horizon_dem import DEM
        dem = DEM(args.dem_dir)
        start, goal = tuple(args.start or REAL_START), tuple(args.goal or REAL_GOAL)
        source = 'LOLA terrain — computed candidate rover route'
    sampled = RecordedDEM(dem)
    result = plan_rover_route(sampled, start, goal, max_slope_deg=args.max_slope_deg,
                              cell_size_m=args.cell_size_m, padding_m=args.padding_m,
                              climb_weight=args.climb_weight, slope_weight=args.slope_weight,
                              max_cells=args.max_cells, max_expansions=args.max_expansions)
    plot_route(result, sampled, start, goal, source, args.output)
    report = args.output.with_suffix('.json')
    report.write_text(json.dumps({'source': source, 'result': result}, indent=2, allow_nan=False), encoding='utf-8')
    print(f"Expanded nodes: {result['expanded_nodes']}; boundary reached: {result['search_boundary_reached']}")
    print(f"Status: {result['status']}\nPlot: {args.output.resolve()}\nReport: {report.resolve()}")
    return 0 if result['status'] == 'route_found' else 2


if __name__ == '__main__':
    raise SystemExit(main())
