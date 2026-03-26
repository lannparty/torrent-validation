/// CPU reference implementations for debris flow initiation (Staley et al. 2017)
/// and runout (Voellmy 1955 rheology with Hungr 1995 entrainment).
pub mod cpu_reference {
    const GRAVITY: f32 = 9.81;
    const MIN_DEPTH: f32 = 0.001;

    // =========================================================================
    // Debris Flow Initiation — Staley et al. (2017) logistic regression
    // =========================================================================

    /// Input parameters for debris flow initiation probability.
    /// Per-drainage basin aggregated values.
    #[derive(Debug, Clone, Copy)]
    pub struct InitiationInput {
        /// 15-minute peak rainfall accumulation (mm)
        pub rainfall_15min_mm: f32,
        /// Proportion of upslope area burned mod/high severity AND gradient >= 23° (0-1)
        pub burned_steep_fraction: f32,
        /// Average dNBR of upslope area (raw dNBR units, typically 0-1000)
        pub avg_dnbr: f32,
        /// Soil KF-factor (USDA erodibility factor, area-weighted average)
        pub soil_kf: f32,
    }

    /// Published coefficients from Staley et al. (2016), USGS OFR 2016-1106.
    ///
    /// The USGS M1 likelihood model (operational standard):
    ///   X = B0 + B1·X1R + B2·X2R + B3·X3R
    /// where ALL predictor terms are interactions with 15-min rainfall:
    ///   X1R = (proportion burned mod/high with slope ≥ 23°) × I15
    ///   X2R = (average dNBR / 1000) × I15
    ///   X3R = (soil KF-factor) × I15
    ///
    /// Source: https://pubs.usgs.gov/of/2016/1106/ofr20161106.pdf, Table 3
    /// Also: https://www.usgs.gov/programs/landslide-hazards/science/scientific-background
    const B0: f32 = -3.63;  // intercept
    const B1: f32 = 0.41;   // X1R: burned steep area × rainfall
    const B2: f32 = 0.67;   // X2R: average dNBR/1000 × rainfall
    const B3: f32 = 0.70;   // X3R: soil KF × rainfall

    /// Model version identifier for traceability.
    pub const STALEY_M1_VERSION: &str = "staley_m1_v2_ofr2016-1106";

    /// Compute probability of debris flow initiation.
    ///
    /// Returns probability in range [0, 1] using Staley et al. (2016) M1 model.
    /// All three predictor terms are interaction terms with 15-min rainfall.
    ///
    /// P(DF) = 1 / (1 + e^(-X))
    pub fn initiation_probability(input: &InitiationInput) -> f32 {
        let i15 = input.rainfall_15min_mm;

        // X1R: proportion of area burned mod/high AND steep (≥23°), × rainfall
        let x1r = input.burned_steep_fraction * i15;

        // X2R: average dNBR (normalized to 0-1 range), × rainfall
        let x2r = (input.avg_dnbr / 1000.0) * i15;

        // X3R: soil KF-factor, × rainfall
        let x3r = input.soil_kf * i15;

        let x = B0 + B1 * x1r + B2 * x2r + B3 * x3r;

        // Logistic function: P = 1 / (1 + e^(-x))
        let p = 1.0 / (1.0 + (-x).exp());
        p.clamp(0.0, 1.0)
    }

    // =========================================================================
    // Debris Flow Runout — Voellmy (1955) rheology
    // =========================================================================

    /// Voellmy rheology parameters.
    #[derive(Debug, Clone, Copy)]
    pub struct VoellmyParams {
        /// Dry Coulomb friction coefficient μ (typically 0.1-0.2)
        pub mu: f32,
        /// Turbulent friction coefficient ξ (m/s², typically 200-1000)
        pub xi: f32,
        /// Entrainment coefficient (Hungr 1995), typically 0.001-0.01
        pub entrainment_coeff: f32,
        /// Density of debris flow material (kg/m³)
        pub density: f32,
    }

    impl Default for VoellmyParams {
        fn default() -> Self {
            Self {
                mu: 0.15,
                xi: 500.0,
                entrainment_coeff: 0.005,
                density: 2000.0,
            }
        }
    }

    /// A snapshot of the depth grid at a specific simulation time.
    #[derive(Debug, Clone)]
    pub struct FlowSnapshot {
        pub time_seconds: f64,
        pub depth: Vec<f32>,
    }

    /// Statistics from runout simulation.
    #[derive(Debug)]
    pub struct RunoutStats {
        pub total_steps: u64,
        pub final_time: f64,
        pub max_depth: f32,
        pub max_velocity: f32,
        pub total_volume: f32,
        /// Seconds until flow first reaches each cell (f32::INFINITY = never reached).
        pub arrival_time: Vec<f32>,
        /// Depth-grid snapshots captured at regular intervals during simulation.
        pub snapshots: Vec<FlowSnapshot>,
    }

    /// Compute Voellmy friction slope.
    ///
    /// Sf = μ·g·cos(θ) + g·u²/(ξ·h)
    ///
    /// Returns friction deceleration (m/s²) in the direction opposing flow.
    fn voellmy_friction(speed: f32, depth: f32, slope: f32, params: &VoellmyParams) -> f32 {
        if depth < MIN_DEPTH || speed < 1e-6 {
            return 0.0;
        }
        let cos_theta = 1.0 / (1.0 + slope * slope).sqrt();
        let coulomb = params.mu * GRAVITY * cos_theta;
        let turbulent = GRAVITY * speed * speed / (params.xi * depth);
        coulomb + turbulent
    }

    /// Compute CFL-limited timestep for the debris flow solver.
    fn compute_dt(depth: &[f32], vel_x: &[f32], vel_y: &[f32], dx: f32, cfl: f32) -> f32 {
        // wave_speed_factor = 1.0 for HLL-type debris flow solver
        crate::solver_utils::compute_dt(depth, vel_x, vel_y, dx, cfl, 1.0)
    }

    /// Run Voellmy debris flow runout solver.
    ///
    /// Uses a Godunov-type finite volume scheme similar to shallow water,
    /// but with Voellmy friction instead of Manning friction, plus
    /// bed entrainment (Hungr 1995).
    ///
    /// # Arguments
    /// * `elevation` - bed elevation (m), modified in place if entrainment active
    /// * `depth` - flow depth (m), modified in place
    /// * `vel_x`, `vel_y` - velocity components (m/s), modified in place
    /// * `erodible_depth` - available erodible bed thickness (m), modified in place
    /// * `rows`, `cols` - grid dimensions
    /// * `cell_size` - cell size (m)
    /// * `total_time` - simulation end time (s)
    /// * `cfl` - CFL number
    /// * `params` - Voellmy rheology parameters
    #[allow(clippy::too_many_arguments)]
    pub fn runout(
        elevation: &mut [f32],
        depth: &mut [f32],
        vel_x: &mut [f32],
        vel_y: &mut [f32],
        erodible_depth: &mut [f32],
        rows: u32,
        cols: u32,
        cell_size: f64,
        total_time: f64,
        cfl: f32,
        params: &VoellmyParams,
    ) -> Result<RunoutStats, String> {
        let dx = cell_size as f32;
        let n = (rows * cols) as usize;
        let mut t = 0.0f64;
        let mut step_count = 0u64;
        let mut max_velocity = 0.0f32;
        let cfl = cfl.min(0.4); // Clamp for stability on steep terrain

        let mut depth_new = vec![0.0f32; n];
        let mut momx_new = vec![0.0f32; n];
        let mut momy_new = vec![0.0f32; n];

        // Arrival time tracking: INFINITY until flow first reaches each cell
        let mut arrival_time = vec![f32::INFINITY; n];
        // Seed arrival time for cells that already have flow at t=0
        for idx in 0..n {
            if depth[idx] > MIN_DEPTH {
                arrival_time[idx] = 0.0;
            }
        }

        // Snapshot capture at regular intervals
        let snapshot_interval = 30.0; // seconds
        let mut next_snapshot = snapshot_interval;
        let mut snapshots: Vec<FlowSnapshot> = Vec::new();

        while t < total_time {
            let dt = compute_dt(depth, vel_x, vel_y, dx, cfl)
                .min((total_time - t) as f32);

            if dt < 1e-10 {
                break;
            }

            // Check if any flow remains
            let has_flow = depth.iter().any(|&h| h > MIN_DEPTH);
            if !has_flow {
                break;
            }

            // Tiled iteration for cache locality on wide grids (optimized for
            // AMD 9950X3D 128 MB V-Cache). Produces identical results to flat iteration.
            const TILE_SIZE: usize = 64;

            for ti in (0..rows as usize).step_by(TILE_SIZE) {
                for tj in (0..cols as usize).step_by(TILE_SIZE) {
                    let ti_end = (ti + TILE_SIZE).min(rows as usize);
                    let tj_end = (tj + TILE_SIZE).min(cols as usize);
                    for i in ti..ti_end {
                        for j in tj..tj_end {
                    let idx = i * cols as usize + j;
                    let h = depth[idx];
                    let ux = vel_x[idx];
                    let uy = vel_y[idx];
                    let z = elevation[idx];

                    // Hydrostatic reconstruction (Audusse et al. 2004) for
                    // well-balanced bed slope treatment on steep terrain.
                    // X-direction with hydrostatic reconstruction
                    let (fx_l_mass, fx_l_mom, pc_xl) = if j > 0 {
                        let z_nb = elevation[idx - 1];
                        let h_nb = depth[idx - 1];
                        let u_nb = vel_x[idx - 1];
                        let z_star = z_nb.max(z);
                        let h_l_star = ((z_nb + h_nb) - z_star).max(0.0);
                        let h_r_star = ((z + h) - z_star).max(0.0);
                        let (fm, fmom) = debris_flux(h_l_star, u_nb, h_r_star, ux);
                        (fm, fmom, 0.5 * GRAVITY * (h * h - h_r_star * h_r_star))
                    } else {
                        (0.0, 0.0, 0.0)
                    };

                    let (fx_r_mass, fx_r_mom, pc_xr) = if j < cols as usize - 1 {
                        let z_nb = elevation[idx + 1];
                        let h_nb = depth[idx + 1];
                        let u_nb = vel_x[idx + 1];
                        let z_star = z.max(z_nb);
                        let h_l_star = ((z + h) - z_star).max(0.0);
                        let h_r_star = ((z_nb + h_nb) - z_star).max(0.0);
                        let (fm, fmom) = debris_flux(h_l_star, ux, h_r_star, u_nb);
                        (fm, fmom, 0.5 * GRAVITY * (h * h - h_l_star * h_l_star))
                    } else {
                        (0.0, 0.0, 0.0)
                    };

                    let (fy_b_mass, fy_b_mom, pc_yb) = if i > 0 {
                        let z_nb = elevation[idx - cols as usize];
                        let h_nb = depth[idx - cols as usize];
                        let v_nb = vel_y[idx - cols as usize];
                        let z_star = z_nb.max(z);
                        let h_l_star = ((z_nb + h_nb) - z_star).max(0.0);
                        let h_r_star = ((z + h) - z_star).max(0.0);
                        let (fm, fmom) = debris_flux(h_l_star, v_nb, h_r_star, uy);
                        (fm, fmom, 0.5 * GRAVITY * (h * h - h_r_star * h_r_star))
                    } else {
                        (0.0, 0.0, 0.0)
                    };

                    let (fy_t_mass, fy_t_mom, pc_yt) = if i < rows as usize - 1 {
                        let z_nb = elevation[idx + cols as usize];
                        let h_nb = depth[idx + cols as usize];
                        let v_nb = vel_y[idx + cols as usize];
                        let z_star = z.max(z_nb);
                        let h_l_star = ((z + h) - z_star).max(0.0);
                        let h_r_star = ((z_nb + h_nb) - z_star).max(0.0);
                        let (fm, fmom) = debris_flux(h_l_star, uy, h_r_star, v_nb);
                        (fm, fmom, 0.5 * GRAVITY * (h * h - h_l_star * h_l_star))
                    } else {
                        (0.0, 0.0, 0.0)
                    };

                    let dtdx = dt / dx;
                    let h_new = h - dtdx * (fx_r_mass - fx_l_mass + fy_t_mass - fy_b_mass);
                    // Momentum with well-balanced pressure corrections (replaces explicit bed slope)
                    let hu_new = h * ux - dtdx * (fx_r_mom - fx_l_mom)
                        + dtdx * (pc_xr + pc_xl);
                    let hv_new = h * uy - dtdx * (fy_t_mom - fy_b_mom)
                        + dtdx * (pc_yt + pc_yb);

                    // Voellmy friction source (opposes flow direction)
                    let speed = (ux * ux + uy * uy).sqrt();
                    let (frx, fry) = if h > MIN_DEPTH && speed > 1e-6 {
                        // Compute local slope magnitude for friction
                        let local_slope = if j > 0 && j < cols as usize - 1 && i > 0 && i < rows as usize - 1 {
                            let dzdx = (elevation[idx + 1] - elevation[idx - 1]) / (2.0 * dx);
                            let dzdy = (elevation[idx + cols as usize] - elevation[idx - cols as usize]) / (2.0 * dx);
                            (dzdx * dzdx + dzdy * dzdy).sqrt()
                        } else {
                            0.0
                        };
                        let sf = voellmy_friction(speed, h, local_slope, params);
                        let decel = sf.min(speed / dt); // Limit to prevent reversal
                        (-decel * ux / speed * h, -decel * uy / speed * h)
                    } else {
                        (0.0, 0.0)
                    };

                    depth_new[idx] = h_new.max(0.0);
                    momx_new[idx] = hu_new + dt * (frx);
                    momy_new[idx] = hv_new + dt * (fry);
                }
                    }
                }
            }

            // Update primitives and apply entrainment
            for idx in 0..n {
                depth[idx] = depth_new[idx];
                if depth[idx] > MIN_DEPTH {
                    // Clamp velocity MAGNITUDE (not components independently)
                    const MAX_DF_VELOCITY: f32 = 20.0; // m/s — max observed debris flow
                    let mut vx = momx_new[idx] / depth[idx];
                    let mut vy = momy_new[idx] / depth[idx];
                    let speed = (vx * vx + vy * vy).sqrt();
                    if speed > MAX_DF_VELOCITY {
                        let scale = MAX_DF_VELOCITY / speed;
                        vx *= scale;
                        vy *= scale;
                    }
                    vel_x[idx] = vx;
                    vel_y[idx] = vy;
                    let speed = speed.min(MAX_DF_VELOCITY);
                    max_velocity = max_velocity.max(speed);

                    // Hungr (1995) entrainment: erosion rate ∝ flow velocity
                    // E = Es × |u| × dt (depth of bed eroded per timestep)
                    if erodible_depth[idx] > 0.0 && speed > 0.1 {
                        let eroded = (params.entrainment_coeff * speed * dt)
                            .min(erodible_depth[idx]);
                        depth[idx] += eroded;
                        erodible_depth[idx] -= eroded;
                        elevation[idx] -= eroded;
                    }
                } else {
                    vel_x[idx] = 0.0;
                    vel_y[idx] = 0.0;
                    depth[idx] = 0.0;
                }
            }

            t += dt as f64;
            step_count += 1;

            // Track first arrival time at each cell
            for idx in 0..n {
                if depth[idx] > MIN_DEPTH && arrival_time[idx] == f32::INFINITY {
                    arrival_time[idx] = t as f32;
                }
            }

            // Capture depth snapshot at regular intervals
            if t >= next_snapshot {
                snapshots.push(FlowSnapshot {
                    time_seconds: t,
                    depth: depth.to_vec(),
                });
                next_snapshot += snapshot_interval;
            }
        }

        Ok(RunoutStats {
            total_steps: step_count,
            final_time: t,
            max_depth: depth.iter().cloned().fold(0.0f32, f32::max),
            max_velocity,
            total_volume: depth.iter().sum::<f32>() * dx * dx,
            arrival_time,
            snapshots,
        })
    }

    /// HLL flux for debris flow (same structure as shallow water HLLC but simplified).
    fn debris_flux(h_l: f32, u_l: f32, h_r: f32, u_r: f32) -> (f32, f32) {
        let c_l = if h_l > MIN_DEPTH { (GRAVITY * h_l).sqrt() } else { 0.0 };
        let c_r = if h_r > MIN_DEPTH { (GRAVITY * h_r).sqrt() } else { 0.0 };

        let s_l = u_l - c_l;
        let s_r = u_r + c_r;

        if h_l < MIN_DEPTH && h_r < MIN_DEPTH {
            return (0.0, 0.0);
        }

        if s_l >= 0.0 {
            let f_mass = h_l * u_l;
            let f_mom = h_l * u_l * u_l + 0.5 * GRAVITY * h_l * h_l;
            return (f_mass, f_mom);
        }

        if s_r <= 0.0 {
            let f_mass = h_r * u_r;
            let f_mom = h_r * u_r * u_r + 0.5 * GRAVITY * h_r * h_r;
            return (f_mass, f_mom);
        }

        // HLL average flux
        let f_l_mass = h_l * u_l;
        let f_l_mom = h_l * u_l * u_l + 0.5 * GRAVITY * h_l * h_l;
        let f_r_mass = h_r * u_r;
        let f_r_mom = h_r * u_r * u_r + 0.5 * GRAVITY * h_r * h_r;

        let denom = s_r - s_l + 1e-30;
        let f_mass = (s_r * f_l_mass - s_l * f_r_mass + s_l * s_r * (h_r - h_l)) / denom;
        let f_mom = (s_r * f_l_mom - s_l * f_r_mom + s_l * s_r * (h_r * u_r - h_l * u_l)) / denom;
        (f_mass, f_mom)
    }
}

#[cfg(test)]
mod tests {
    use super::cpu_reference::*;

    #[test]
    fn test_initiation_probability_range() {
        // Test various inputs all produce probabilities in [0, 1]
        let cases = [
            InitiationInput { rainfall_15min_mm: 0.0, burned_steep_fraction: 0.0, avg_dnbr: 0.0, soil_kf: 0.3 },
            InitiationInput { rainfall_15min_mm: 50.0, burned_steep_fraction: 1.0, avg_dnbr: 500.0, soil_kf: 0.5 },
            InitiationInput { rainfall_15min_mm: 10.0, burned_steep_fraction: 0.5, avg_dnbr: 300.0, soil_kf: 0.2 },
            InitiationInput { rainfall_15min_mm: 100.0, burned_steep_fraction: 1.0, avg_dnbr: 700.0, soil_kf: 0.1 },
            InitiationInput { rainfall_15min_mm: 1.0, burned_steep_fraction: 0.01, avg_dnbr: 50.0, soil_kf: 0.6 },
        ];

        for (i, input) in cases.iter().enumerate() {
            let p = initiation_probability(input);
            assert!((0.0..=1.0).contains(&p),
                "Case {i}: probability {p} out of range for input {input:?}");
        }
    }

    #[test]
    fn test_initiation_increases_with_rainfall() {
        // All 3 terms are rainfall interactions, so more rain = higher P
        let low = InitiationInput {
            rainfall_15min_mm: 5.0,
            burned_steep_fraction: 0.5,
            avg_dnbr: 400.0,
            soil_kf: 0.3,
        };
        let high = InitiationInput {
            rainfall_15min_mm: 40.0,
            ..low
        };
        let p_low = initiation_probability(&low);
        let p_high = initiation_probability(&high);
        assert!(p_high > p_low,
            "Higher rainfall should increase probability: p_low={p_low}, p_high={p_high}");
    }

    #[test]
    fn test_initiation_increases_with_burn_severity() {
        let unburned = InitiationInput {
            rainfall_15min_mm: 20.0,
            burned_steep_fraction: 0.0,
            avg_dnbr: 0.0,
            soil_kf: 0.3,
        };
        let burned = InitiationInput {
            burned_steep_fraction: 0.8,
            avg_dnbr: 500.0,
            ..unburned
        };
        let p_ub = initiation_probability(&unburned);
        let p_b = initiation_probability(&burned);
        assert!(p_b > p_ub,
            "Higher burn severity should increase probability: unburned={p_ub}, burned={p_b}");
    }

    #[test]
    fn test_m1_matches_published_example() {
        // Verify against a manual computation of the M1 equation:
        // X = -3.63 + 0.41*(0.6*15) + 0.67*(400/1000*15) + 0.70*(0.3*15)
        //   = -3.63 + 0.41*9 + 0.67*6 + 0.70*4.5
        //   = -3.63 + 3.69 + 4.02 + 3.15
        //   = 7.23
        // P = 1/(1+e^(-7.23)) ≈ 0.99927
        let input = InitiationInput {
            rainfall_15min_mm: 15.0,
            burned_steep_fraction: 0.6,
            avg_dnbr: 400.0,
            soil_kf: 0.3,
        };
        let p = initiation_probability(&input);
        assert!((p - 0.99927).abs() < 0.001,
            "M1 manual check: expected ~0.99927, got {p}");
    }

    #[test]
    fn test_runout_stops_on_flat_terrain() {
        // Debris flow on perfectly flat terrain should decelerate and stop
        let rows = 20u32;
        let cols = 20u32;
        let n = (rows * cols) as usize;
        let cell_size = 10.0;

        let mut elevation = vec![0.0f32; n];
        let mut depth = vec![0.0f32; n];
        let mut vel_x = vec![0.0f32; n];
        let mut vel_y = vec![0.0f32; n];
        let mut erodible = vec![0.0f32; n]; // no entrainment

        // Place initial debris mass in center
        let center = 10 * cols as usize + 10;
        depth[center] = 2.0;
        vel_x[center] = 1.0;

        let params = VoellmyParams {
            mu: 0.15,
            xi: 500.0,
            entrainment_coeff: 0.0,
            ..VoellmyParams::default()
        };

        let stats = runout(
            &mut elevation,
            &mut depth,
            &mut vel_x,
            &mut vel_y,
            &mut erodible,
            rows, cols, cell_size,
            60.0, // 60 seconds
            0.5,
            &params,
        ).unwrap();

        // Flow should have slowed significantly due to friction
        let max_speed: f32 = vel_x.iter().zip(vel_y.iter())
            .map(|(vx, vy)| (vx * vx + vy * vy).sqrt())
            .fold(0.0f32, f32::max);

        assert!(max_speed < 1.0,
            "Flow should decelerate on flat terrain, max_speed={max_speed}");
        assert!(stats.total_steps > 0);
    }

    #[test]
    fn test_runout_volume_conservation_no_entrainment() {
        let rows = 20u32;
        let cols = 20u32;
        let n = (rows * cols) as usize;
        let cell_size = 10.0;
        let dx = cell_size as f32;

        let mut elevation = vec![0.0f32; n];
        let mut depth = vec![0.0f32; n];
        let mut vel_x = vec![0.0f32; n];
        let mut vel_y = vec![0.0f32; n];
        let mut erodible = vec![0.0f32; n];

        // Initial mass
        let center = 10 * cols as usize + 10;
        depth[center] = 3.0;
        let initial_volume = depth.iter().sum::<f32>() * dx * dx;

        let params = VoellmyParams {
            entrainment_coeff: 0.0,
            ..VoellmyParams::default()
        };

        let _stats = runout(
            &mut elevation,
            &mut depth,
            &mut vel_x,
            &mut vel_y,
            &mut erodible,
            rows, cols, cell_size,
            30.0,
            0.5,
            &params,
        ).unwrap();

        let final_volume = depth.iter().sum::<f32>() * dx * dx;
        let rel_error = (final_volume - initial_volume).abs() / initial_volume;
        assert!(rel_error < 0.05,
            "Volume should be conserved without entrainment: initial={initial_volume}, final={final_volume}, rel_error={rel_error}");
    }

    #[test]
    fn test_arrival_time_unreached_cells_are_infinity() {
        // Cells that flow never reaches should have arrival_time = INFINITY
        let rows = 20u32;
        let cols = 20u32;
        let n = (rows * cols) as usize;
        let cell_size = 10.0;

        let mut elevation = vec![0.0f32; n];
        let mut depth = vec![0.0f32; n];
        let mut vel_x = vec![0.0f32; n];
        let mut vel_y = vec![0.0f32; n];
        let mut erodible = vec![0.0f32; n];

        // Place initial debris in corner — friction will stop it before reaching far cells
        depth[0] = 1.0;

        let params = VoellmyParams {
            mu: 0.3, // high friction to limit spread
            xi: 200.0,
            entrainment_coeff: 0.0,
            ..VoellmyParams::default()
        };

        let stats = runout(
            &mut elevation, &mut depth, &mut vel_x, &mut vel_y, &mut erodible,
            rows, cols, cell_size, 30.0, 0.5, &params,
        ).unwrap();

        // Far corner should never be reached
        let far_corner = (rows as usize - 1) * cols as usize + (cols as usize - 1);
        assert!(
            stats.arrival_time[far_corner] == f32::INFINITY,
            "Far corner should not be reached, got arrival_time={}",
            stats.arrival_time[far_corner]
        );

        // Source cell should have arrival_time = 0 (had flow at t=0)
        assert!(
            stats.arrival_time[0] == 0.0,
            "Source cell should have arrival_time=0, got {}",
            stats.arrival_time[0]
        );
    }

    #[test]
    fn test_arrival_time_increases_with_distance() {
        // On a steep slope, cells further downhill should have later arrival times
        let rows = 40u32;
        let cols = 10u32;
        let n = (rows * cols) as usize;
        let cell_size = 5.0; // smaller cells for faster propagation

        // Create very steep slope: 10m drop per cell
        let mut elevation = vec![0.0f32; n];
        for i in 0..rows as usize {
            for j in 0..cols as usize {
                elevation[i * cols as usize + j] = (rows as f32 - i as f32) * 10.0;
            }
        }

        let mut depth = vec![0.0f32; n];
        let mut vel_x = vec![0.0f32; n];
        let mut vel_y = vec![0.0f32; n];
        let mut erodible = vec![0.5f32; n]; // erodible bed to sustain flow

        // Place substantial debris at top rows
        for i in 1..5 {
            for j in 0..cols as usize {
                depth[i * cols as usize + j] = 3.0;
            }
        }

        let params = VoellmyParams {
            mu: 0.03,  // low friction
            xi: 2000.0, // low turbulent friction
            entrainment_coeff: 0.01,
            ..VoellmyParams::default()
        };

        let stats = runout(
            &mut elevation, &mut depth, &mut vel_x, &mut vel_y, &mut erodible,
            rows, cols, cell_size, 120.0, 0.5, &params,
        ).unwrap();

        // Find two reached cells at different distances downhill and verify ordering
        let mid_col = cols as usize / 2;
        // Look for first and second reached rows below initiation
        let mut reached_rows: Vec<(usize, f32)> = Vec::new();
        for i in 5..rows as usize {
            let at = stats.arrival_time[i * cols as usize + mid_col];
            if at.is_finite() {
                reached_rows.push((i, at));
            }
        }

        assert!(
            reached_rows.len() >= 2,
            "At least 2 rows below source should be reached, got {}",
            reached_rows.len()
        );

        // Arrival times should be monotonically non-decreasing with row index
        for w in reached_rows.windows(2) {
            assert!(
                w[1].1 >= w[0].1,
                "Arrival time should not decrease with distance: row{}={}, row{}={}",
                w[0].0, w[0].1, w[1].0, w[1].1
            );
        }

        // First and last reached rows should have different arrival times
        let first = reached_rows.first().unwrap();
        let last = reached_rows.last().unwrap();
        assert!(
            last.1 > first.1,
            "Furthest reached cell should arrive later: row{}={}, row{}={}",
            first.0, first.1, last.0, last.1
        );
    }

    #[test]
    fn test_snapshots_captured_at_intervals() {
        // Snapshots should be captured roughly every 30 simulated seconds
        let rows = 30u32;
        let cols = 10u32;
        let n = (rows * cols) as usize;
        let cell_size = 10.0;

        let mut elevation = vec![0.0f32; n];
        for i in 0..rows as usize {
            for j in 0..cols as usize {
                elevation[i * cols as usize + j] = (rows as f32 - i as f32) * 5.0;
            }
        }

        let mut depth = vec![0.0f32; n];
        let mut vel_x = vec![0.0f32; n];
        let mut vel_y = vec![0.0f32; n];
        let mut erodible = vec![0.1f32; n];

        for j in 0..cols as usize {
            depth[2 * cols as usize + j] = 2.0;
        }

        let params = VoellmyParams {
            mu: 0.05,
            xi: 1000.0,
            entrainment_coeff: 0.005,
            ..VoellmyParams::default()
        };

        let stats = runout(
            &mut elevation, &mut depth, &mut vel_x, &mut vel_y, &mut erodible,
            rows, cols, cell_size, 120.0, 0.5, &params,
        ).unwrap();

        // With 120s total and 30s interval, expect ~3-4 snapshots
        assert!(
            !stats.snapshots.is_empty(),
            "Should capture at least one snapshot in 120s simulation"
        );

        // Snapshots should be in ascending time order
        for w in stats.snapshots.windows(2) {
            assert!(
                w[1].time_seconds > w[0].time_seconds,
                "Snapshots should be in time order"
            );
        }

        // Each snapshot depth grid should have the right length
        for snap in &stats.snapshots {
            assert_eq!(snap.depth.len(), n, "Snapshot depth grid should match grid size");
        }

        // First snapshot should be around 30s
        if !stats.snapshots.is_empty() {
            assert!(
                stats.snapshots[0].time_seconds >= 29.0 && stats.snapshots[0].time_seconds <= 35.0,
                "First snapshot should be near 30s, got {}",
                stats.snapshots[0].time_seconds
            );
        }
    }

    #[test]
    fn test_entrainment_increases_volume() {
        let rows = 30u32;
        let cols = 10u32;
        let n = (rows * cols) as usize;
        let cell_size = 10.0;
        let dx = cell_size as f32;

        // Create a steep slope to drive flow
        let mut elevation = vec![0.0f32; n];
        for i in 0..rows as usize {
            for j in 0..cols as usize {
                elevation[i * cols as usize + j] = (rows as f32 - i as f32) * 5.0; // 5m drop per cell
            }
        }

        let mut depth = vec![0.0f32; n];
        let mut vel_x = vec![0.0f32; n];
        let mut vel_y = vec![0.0f32; n];
        let mut erodible = vec![1.0f32; n]; // 1m of erodible bed everywhere

        // Place debris at top
        for j in 0..cols as usize {
            let idx = 2 * cols as usize + j;
            depth[idx] = 2.0;
        }

        let initial_volume: f32 = depth.iter().sum::<f32>() * dx * dx;

        let params = VoellmyParams {
            mu: 0.05,
            xi: 1000.0,
            entrainment_coeff: 0.01,
            ..VoellmyParams::default()
        };

        let _stats = runout(
            &mut elevation,
            &mut depth,
            &mut vel_x,
            &mut vel_y,
            &mut erodible,
            rows, cols, cell_size,
            30.0,
            0.5,
            &params,
        ).unwrap();

        let final_volume = depth.iter().sum::<f32>() * dx * dx;
        assert!(final_volume > initial_volume,
            "Entrainment should increase total volume: initial={initial_volume}, final={final_volume}");
    }
}
