"""
Normative constants used throughout the rc-column-checker calculations.
Each constant is labelled with the code clause it comes from so that a
reviewer can trace every numeric value back to its source document.
"""

# ---------------------------------------------------------------------------
# ACI 318-22  — Material model for concrete
# ---------------------------------------------------------------------------
ACI_ALPHA1 = 0.85          # Concrete compression block coefficient  (ACI 22.2.1.3)
ACI_ECU = 0.003            # Ultimate concrete compressive strain     (ACI 22.2.2.1)
ACI_BETA1_FC_PIVOT = 28.0  # f'c at which beta1 starts to reduce, MPa (ACI Table 22.2.2.4.3)
ACI_BETA1_MAX = 0.85       # Maximum value of beta1                   (ACI Table 22.2.2.4.3)
ACI_BETA1_MIN = 0.65       # Minimum value of beta1                   (ACI Table 22.2.2.4.3)
ACI_BETA1_SLOPE = 0.05     # beta1 reduction per 7 MPa above pivot    (ACI Table 22.2.2.4.3)
ACI_BETA1_FC_STEP = 7.0    # MPa step for beta1 reduction             (ACI Table 22.2.2.4.3)

# ---------------------------------------------------------------------------
# ACI 318-22  — Material model for steel
# ---------------------------------------------------------------------------
ACI_ES_MPA = 200_000.0     # Modulus of elasticity of steel, MPa      (ACI 20.2.2.2)

# ---------------------------------------------------------------------------
# ACI 318-22  — Strength reduction factors (phi)
# ---------------------------------------------------------------------------
ACI_PHI_COMPRESSION = 0.65          # Compression-controlled sections  (ACI Table 21.2.2)
ACI_PHI_TENSION = 0.90              # Tension-controlled sections       (ACI Table 21.2.2)
ACI_PHI_TRANSITION_STRAIN = 0.003   # Strain range over which phi transitions (ACI 21.2.2)
ACI_PHI_SHEAR = 0.75                # Shear and torsion                 (ACI Table 21.2.1(c))
ACI_PHI_JOINT = 0.85                # Beam-column joints                (ACI Table 21.2.1(d))

# ---------------------------------------------------------------------------
# ACI 318-22  — Axial capacity (nominal concentric)
# ---------------------------------------------------------------------------
ACI_VC_COEFF = 0.17                 # Simplified Vc coefficient, sqrt(f'c)*bw*d  (ACI 22.5.5.1)
ACI_VC_ZERO_AXIAL_DIVISOR = 20.0   # Vc=0 when Pu < Ag*f'c / 20               (ACI 18.7.6.2.1)

# ---------------------------------------------------------------------------
# ACI 318-22  — Seismic detailing (Chapter 18)
# ---------------------------------------------------------------------------
ACI_SCWB_FACTOR = 1.2              # Strong-column weak-beam ratio             (ACI 18.7.3.2)
ACI_FYE_FACTOR = 1.25              # Probable flexural strength factor (fye/fy) (ACI 18.6.5 / ASCE 41)

# ACI 18.7.5 — Confinement region lo
ACI_LO_MIN_MM = 450.0              # Absolute minimum confinement length       (ACI 18.7.5.1)
ACI_LO_HEIGHT_DIVISOR = 6.0        # lo >= lclear / 6                          (ACI 18.7.5.1)

# ACI 18.7.5.2 — Lateral support limits
ACI_HOOK_ANGLE_MIN_DEG = 135.0     # Minimum hook angle for rectilinear hoops  (ACI 18.7.5.2(b))
ACI_HX_GENERAL_MM = 350.0          # Max unsupported bar spacing (general)      (ACI 18.7.5.2(e))
ACI_HX_SPECIAL_MM = 200.0          # Max unsupported bar spacing (high Pu/f'c)  (ACI 18.7.5.2(f))
ACI_HIGH_FC_THRESHOLD_MPA = 70.0   # f'c threshold triggering special hx limit  (ACI 18.7.5.2(f))
ACI_HIGH_AXIAL_FC_RATIO = 0.3      # Pu/(Ag*f'c) threshold for special hx limit (ACI 18.7.5.2(f))

# ACI 18.7.5.3 / 18.7.5.5 — Tie spacing limits
ACI_SO_MIN_MM = 100.0              # Minimum value of so (spacing equation)     (ACI 18.7.5.3)
ACI_SO_MAX_MM = 150.0              # Maximum value of so and outside-lo spacing (ACI 18.7.5.3 / 18.7.5.5)

# ACI Table 18.7.5.4 — Minimum transverse reinforcement ratio, rectangular section
ACI_RHO_S_RECT_A = 0.3             # Coefficient for expression (a)             (ACI Table 18.7.5.4)
ACI_RHO_S_RECT_B = 0.09            # Coefficient for expression (b)             (ACI Table 18.7.5.4)
ACI_RHO_S_RECT_C = 0.2             # Coefficient for expression (c)             (ACI Table 18.7.5.4)

# ACI Table 18.7.5.4 — Minimum transverse reinforcement ratio, circular section
ACI_RHO_S_CIRC_D = 0.45            # Coefficient for expression (d)             (ACI Table 18.7.5.4)
ACI_RHO_S_CIRC_E = 0.12            # Coefficient for expression (e)             (ACI Table 18.7.5.4)
ACI_RHO_S_CIRC_F = 0.35            # Coefficient for expression (f)             (ACI Table 18.7.5.4)

# ACI 18.14.3.2 — Gravity columns in SDC D/E/F
ACI_GRAVITY_AXIAL_TRIGGER = 0.35   # Pu > 0.35*Po triggers additional requirements (ACI 18.14.3.2(c))

# ---------------------------------------------------------------------------
# ASCE 41  — Expected material strength factors (Table 10-4)
# ---------------------------------------------------------------------------
ASCE41_FYE_DEFAULT = 1.25          # Default fye/fy ratio (expected/nominal)    (ASCE 41 Table 10-4)
ASCE41_FYTE_DEFAULT = 1.25         # Default fyte/fyt ratio                     (ASCE 41 Table 10-4)

# ---------------------------------------------------------------------------
# ASCE 41 Table 10-8  — Plastic rotation parameters, RC columns with hoops
# ---------------------------------------------------------------------------

# rho_t limits
ASCE41_RHO_T_MIN = 0.0005          # Lower bound; equations not valid below this (ASCE 41 Table 10-8, note)
ASCE41_RHO_T_CAP_ANCHORED = 0.0175 # Upper cap when ties are adequately anchored (ASCE 41 Table 10-8)
ASCE41_RHO_T_CAP_UNANCHORED = 0.0075  # Upper cap when ties are NOT adequately anchored (ASCE 41 Table 10-8)

# Unspliced column — parameter 'a'
ASCE41_A_INTERCEPT = 0.042         # (ASCE 41 Table 10-8)
ASCE41_A_AXIAL_COEFF = 0.043       # (ASCE 41 Table 10-8)
ASCE41_A_RHOT_COEFF = 0.63         # (ASCE 41 Table 10-8)
ASCE41_A_VRATIO_COEFF = 0.023      # (ASCE 41 Table 10-8)
ASCE41_A_AXIAL_CAP = 0.5           # r_eff = min(axial_ratio, 0.5)              (ASCE 41 Table 10-8)

# Unspliced column — parameter 'b'
ASCE41_B_NUMERATOR = 0.5           # (ASCE 41 Table 10-8)
ASCE41_B_DENOM_INTERCEPT = 5.0     # (ASCE 41 Table 10-8)
ASCE41_B_DENOM_AXIAL_DIV = 0.8     # (ASCE 41 Table 10-8)
ASCE41_B_SUBTRACTION = 0.01        # (ASCE 41 Table 10-8)

# Unspliced column — parameter 'c'
ASCE41_C_INTERCEPT = 0.24          # (ASCE 41 Table 10-8)
ASCE41_C_AXIAL_COEFF = 0.4         # (ASCE 41 Table 10-8)

# High-axial scaling (axial_ratio > 0.5)
ASCE41_HIGH_AXIAL_THRESHOLD = 0.5  # Axial ratio above which degradation scaling starts (ASCE 41 Table 10-8)
ASCE41_HIGH_AXIAL_SCALE_TOP = 0.7  # Numerator in linear scale factor              (ASCE 41 Table 10-8)
ASCE41_HIGH_AXIAL_SCALE_RANGE = 0.2 # Denominator (range) in linear scale factor   (ASCE 41 Table 10-8)

# Spliced column — parameter bounds
ASCE41_SP_A_CAP = 0.025            # Maximum a for splice-controlled columns    (ASCE 41 Table 10-8)
ASCE41_SP_B_CAP = 0.06             # Maximum b for splice-controlled columns    (ASCE 41 Table 10-8)
ASCE41_SP_B_INTERCEPT = 0.012      # (ASCE 41 Table 10-8)
ASCE41_SP_B_AXIAL_COEFF = 0.085    # (ASCE 41 Table 10-8)
ASCE41_SP_B_RHOT_COEFF = 12.0      # (ASCE 41 Table 10-8)
ASCE41_SP_C_CAP = 0.4              # Maximum c for splice-controlled columns    (ASCE 41 Table 10-8)
ASCE41_SP_C_INTERCEPT = 0.15       # (ASCE 41 Table 10-8)
ASCE41_SP_C_RHOT_COEFF = 36.0      # (ASCE 41 Table 10-8)
ASCE41_SP_A_DENOM_COEFF = 8.0      # Denominator coefficient for a_sp           (ASCE 41 Table 10-8)

# Acceptance criteria conversion factors
ASCE41_THETA_IO_FACTOR = 0.15      # theta_io = min(factor * a, max)            (ASCE 41 Table 10-8)
ASCE41_THETA_IO_MAX = 0.005        # Absolute max for theta_io                  (ASCE 41 Table 10-8)
ASCE41_THETA_LS_FACTOR = 0.5       # theta_ls = factor * b                      (ASCE 41 Table 10-8)
ASCE41_THETA_CP_FACTOR = 0.7       # theta_cp = factor * b                      (ASCE 41 Table 10-8)

# Minimum Vye/VColOE ratio used in screening
ASCE41_V_RATIO_MIN = 0.2           # Not less than 0.2 per ASCE 41 commentary   (ASCE 41 Table 10-8)
