"""Verified optics operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "image_distance",
        "optics",
        "Thin-lens and mirror equation",
        "v",
        base_latex="\\frac{1}{f} = \\frac{1}{u} + \\frac{1}{v}",
        variables=(
            var("d_obj", "u", "meter"),
            var("focal", "f", "meter"),
            # Not in the formula: a lens and a concave mirror share it, and
            # only the ray diagram tells them apart.
            var("mirror", "mirror", dimensionless=True, visible=False),
        ),
    ),
    formula(
        "magnification",
        "optics",
        "Magnification formula",
        "m",
        variables=(
            var("h_img", "h_i", "meter"),
            var("h_obj", "h_o", "meter"),
        ),
    ),
    formula(
        "light_speed_in_medium",
        "optics",
        "Refractive-index definition",
        "v",
        base_latex=r"v = \frac{c}{n}",
        expression="c_light/n_index",
        variables=(
            var(
                "n_index",
                "n",
                dimensionless=True,
                words=("refractive index", "index of refraction", "n ="),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("speed of light in", "speed of light", "speed in", "speed"),
            result=("meter / second",),
            inputs=(frozenset({"n_index"}),),
            cues=("light",),
            nonnegative=True,
        ),
    ),
    formula(
        "refractive_index",
        "optics",
        "Snell's law",
        "n",
        variables=(
            var("angle", r"\theta", dimensionless=True),
            var("angle2", r"\theta_2", dimensionless=True),
            var("v_wave", "v", "meter / second"),
        ),
    ),
    # The law of reflection. A ray given against the mirror's surface is
    # turned to the normal first: 35 degrees to the surface is 55 to the normal.
    *(
        formula(
            operation,
            "optics",
            "Law of reflection",
            symbol,
            base_latex="\\theta_r = \\theta_i",
            variables=(
                var("angle", "\\theta_i", dimensionless=True),
                var("angle_surface", "\\alpha", dimensionless=True),
            ),
        )
        for operation, symbol in (
            ("reflection_angle", "\\theta_r"),
            ("reflection_surface_angle", "\\beta"),
            ("reflection_ray_angle", "\\theta_i + \\theta_r"),
        )
    ),
    formula(
        "critical_angle",
        "optics",
        "Critical-angle equation",
        "\\theta_c",
        variables=(var("n1", "n_1", dimensionless=True),),
    ),
    formula(
        "lens_power",
        "optics",
        "Lens-power formula",
        "P",
        base_latex="P = \\frac{1}{f}",
        # Only a length called the focal length is f: a myopic eye's far point
        # of 80 cm was certified +1.25 D (the lens is concave, -1.25 D).
        variables=(
            var(
                "focal",
                "f",
                "meter",
                words=("focal length", "focal", "f =", "f="),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("power",),
            result=("1 / meter",),
            inputs=(frozenset({"focal"}),),
            cues=("lens", "magnifying glass", "magnifier", "spectacles", "eyeglass"),
            # A diverging lens's power is negative, and so is a short-sighted eye's:
            # its sign is the convention an unsigned focal length leaves unstated.
            excludes=("concave", "diverging", "myopi", "short-sight", "short sight", "near-sight"),
        ),
    ),
    formula(
        "snell_refraction_angle",
        "optics",
        "Snell's law",
        r"\theta_2",
        base_latex=r"n_1 \sin\theta_1 = n_2 \sin\theta_2",
        expression="asin(n1*sin(angle)/n2)*180/pi",
        # "30 degrees to the surface" is 60 to the normal. Read as 30, it
        # certified 19.47 degrees for glass instead of 35.26.
        variants=(
            FormulaVariant(
                latex=r"n_1 \sin(90^\circ - \alpha) = n_2 \sin\theta_2",
                present=frozenset({"from_surface"}),
                expression="asin(n1*cos(angle)/n2)*180/pi",
            ),
        ),
        variables=(
            var("angle", r"\theta_1", dimensionless=True),
            var(
                "from_surface",
                "",
                dimensionless=True,
                visible=False,
                implied=(
                    ("to the surface", 1.0),
                    ("with the surface", 1.0),
                    ("from the surface", 1.0),
                    ("relative to the surface", 1.0),
                    ("to the boundary", 1.0),
                    ("with the boundary", 1.0),
                    ("to the interface", 1.0),
                    ("glancing angle", 1.0),
                    ("grazing angle", 1.0),
                ),
            ),
            # "Light strikes a glass block (n = 1.5)" comes from air: the one
            # index stated is the medium it enters. Light that starts inside a
            # medium ("leaves", "inside", "from glass") never takes air's.
            var(
                "n1",
                "n_1",
                dimensionless=True,
                words=("from", "leaves", "travelling in", "traveling in"),
                implied=(("from air", 1.0), ("in air", 1.0), ("from a vacuum", 1.0)),
                fallback="incident_from_air",
            ),
            var(
                "n2",
                "n_2",
                dimensionless=True,
                words=(
                    "into",
                    "enters",
                    "entering",
                    "strikes",
                    "hits",
                    "incident on",
                    "falls on",
                ),
            ),
        ),
        binding=Binding(
            asks=("angle of refraction", "refraction angle", "refracted angle"),
            result=("degree",),
            inputs=(
                frozenset({"angle", "n1", "n2"}),
                frozenset({"angle", "from_surface", "n1", "n2"}),
            ),
            nonnegative=True,
        ),
    ),
    formula(
        "mirror_focal_length",
        "optics",
        "Spherical-mirror focal length",
        "f",
        base_latex=r"f = \frac{R}{2}",
        assumptions=("a spherical mirror, rays near the axis",),
        expression="radius_curvature/2",
        variables=(var("radius_curvature", "R", "meter"),),
        binding=Binding(
            asks=("focal length",),
            result=("meter",),
            inputs=(frozenset({"radius_curvature"}),),
            cues=("mirror",),
            # A convex mirror's focal length is negative; its sign is the
            # convention the question has not stated.
            excludes=("convex", "diverging"),
            nonnegative=True,
        ),
    ),
    formula(
        "magnification_distances",
        "optics",
        "Magnification equation",
        "m",
        base_latex=r"m = -\frac{v}{u}",
        assumptions=("real distances are positive; a negative m is an inverted image",),
        expression="-d_img/d_obj",
        variables=(
            var("d_img", "v", "meter", words=("image",)),
            var("d_obj", "u", "meter", words=("object",)),
        ),
        binding=Binding(
            asks=("magnification",),
            result=("dimensionless",),
            inputs=(frozenset({"d_img", "d_obj"}),),
            # A virtual, erect or "signed" image's distance carries the other sign, and any place
            # named may be the image's (optic_elements._PLACE). Heights are not u and v.
            excludes=(
                *("virtual", "erect", "upright", "behind", "beyond", "side", "in front", "left of"),
                *("right of", "diverging", "signed", "telescope", "eyepiece", "objective"),
                *("height", "tall", "high"),
            ),
        ),
    ),
    formula(
        "lens_power_sum",
        "optics",
        "Thin lenses in contact",
        "P",
        base_latex=r"P = P_1 + P_2",
        assumptions=("the lenses are thin and in contact",),
        expression="p1+p2",
        variables=(
            var("p1", "P_1", "1 / meter"),
            var("p2", "P_2", "1 / meter"),
        ),
        binding=Binding(
            asks=("power", "lens power", "total power"),
            result=("1 / meter",),
            inputs=(frozenset({"p1", "p2"}),),
            cues=("in contact",),
            interchangeable=("p1", "p2"),
            excludes=("telescope", "diverging"),  # a concave lens's power is negative
            nonnegative=True,
        ),
    ),
    formula(
        "telescope_magnification",
        "optics",
        "Telescope angular magnification",
        "M",
        base_latex=r"M = \frac{f_o}{f_e}",
        assumptions=("the magnitude for an astronomical telescope in normal adjustment",),
        expression="focal_obj/focal_eye",
        variables=(
            var("focal_obj", "f_o", "meter", words=("objective",), needs_words=True),
            var("focal_eye", "f_e", "meter", words=("eyepiece",), needs_words=True),
        ),
        binding=Binding(
            asks=("magnification",),
            result=("dimensionless",),
            inputs=(frozenset({"focal_eye", "focal_obj"}),),
            cues=("telescope",),
            excludes=("microscope",),
            nonnegative=True,
        ),
    ),
    formula(
        "microscope_magnification",
        "optics",
        "Compound microscope magnification",
        "M",
        base_latex=r"M = \frac{L D}{f_o f_e}",
        assumptions=("normal adjustment, and the magnitude",),
        expression="tube_length*near_point/(focal_obj*focal_eye)",
        variables=(
            var("tube_length", "L", "meter", words=("tube",), needs_words=True),
            var(
                "near_point",
                "D",
                "meter",
                words=("near point", "least distance"),
                needs_words=True,
            ),
            var("focal_obj", "f_o", "meter", words=("objective",), needs_words=True),
            var("focal_eye", "f_e", "meter", words=("eyepiece",), needs_words=True),
        ),
        binding=Binding(
            asks=("magnification",),
            result=("dimensionless",),
            inputs=(frozenset({"focal_eye", "focal_obj", "near_point", "tube_length"}),),
            cues=("microscope",),
            excludes=("telescope",),
            nonnegative=True,
        ),
    ),
    formula(
        "lens_maker",
        "optics",
        "Lens-maker equation",
        "f",
        base_latex=r"\frac{1}{f} = (n-1)\left(\frac{1}{R_1}-\frac{1}{R_2}\right)",
        assumptions=("a thin lens in air",),
        expression="1/((n_index-1)*(1/r1-1/r2))",
        variants=(
            FormulaVariant(
                latex=r"\frac{1}{f} = (n-1)\left(\frac{1}{R_1}+\frac{1}{R_2}\right)",
                present=frozenset({"convex"}),
                absent=frozenset({"concave"}),
                expression="1/((n_index-1)*(1/r1+1/r2))",
            ),
            FormulaVariant(
                latex=r"\frac{1}{f} = -(n-1)\left(\frac{1}{R_1}+\frac{1}{R_2}\right)",
                present=frozenset({"concave"}),
                expression="-1/((n_index-1)*(1/r1+1/r2))",
            ),
        ),
        variables=(
            var(
                "n_index",
                "n",
                dimensionless=True,
                words=("refractive index", "index of refraction"),
                needs_words=True,
            ),
            var("r1", "R_1", "meter", words=("first", "r1"), needs_words=False),
            var("r2", "R_2", "meter", words=("second", "r2"), needs_words=False),
            var(
                "convex",
                "",
                dimensionless=True,
                visible=False,
                implied=(("biconvex", 1.0), ("double convex", 1.0), ("convex lens", 1.0)),
            ),
            var(
                "concave",
                "",
                dimensionless=True,
                visible=False,
                implied=(("biconcave", 1.0), ("double concave", 1.0), ("concave lens", 1.0)),
            ),
        ),
        binding=Binding(
            asks=("focal length",),
            result=("meter",),
            inputs=(
                frozenset({"n_index", "r1", "r2"}),
                frozenset({"concave", "n_index", "r1", "r2"}),
                frozenset({"convex", "n_index", "r1", "r2"}),
            ),
            cues=("lens maker", "lensmaker", "radii", "radius of curvature", "biconvex"),
            excludes=("telescope", "microscope", "mirror"),
            interchangeable=("r1", "r2"),
            nonnegative=False,
        ),
    ),
    formula(
        "numerical_aperture",
        "optics",
        "Numerical aperture",
        "NA",
        base_latex=r"\mathrm{NA} = n\sin\theta",
        assumptions=("the half-angle of the acceptance cone",),
        expression="n_index*sin(angle_aperture)",
        variables=(
            var("n_index", "n", dimensionless=True, words=("index",), needs_words=True),
            var("angle_aperture", r"\theta", dimensionless=True),
        ),
        binding=Binding(
            asks=("numerical aperture",),
            result=("dimensionless",),
            inputs=(frozenset({"angle_aperture", "n_index"}),),
            cues=("numerical aperture",),
            nonnegative=True,
        ),
    ),
    # Total internal reflection into air: sin(theta_c) = 1 / n.
    formula(
        "critical_angle_to_air",
        "optics",
        "Critical angle",
        r"\theta_c",
        base_latex=r"\theta_c = \arcsin\frac{1}{n}",
        assumptions=("the light goes from the medium into air (n = 1)",),
        expression="asin(1/n1)*180/pi",
        variables=(var("n1", "n", dimensionless=True, words=("n =", "index", "refractive")),),
        binding=Binding(
            asks=("critical angle",),
            result=("degree",),
            inputs=(frozenset({"n1"}),),
            nonnegative=True,
        ),
    ),
    # The image's height from a converging lens or a concave mirror: the
    # magnification is v/u = f/(u - f). A real image (the object outside F) is
    # inverted, so the signed result is negative and shown as its size,
    # inverted. Inside F the image is virtual, and the sign conventions part.
    formula(
        "image_height",
        "optics",
        "Magnification",
        "h_i",
        base_latex=r"h_i = -h_o\frac{v}{u} = -h_o\frac{f}{u - f}",
        assumptions=("a thin converging lens or a concave mirror, the object outside F",),
        expression="-h_obj*focal/(d_obj - focal)",
        variables=(
            var(
                "h_obj",
                "h_o",
                "meter",
                words=("tall", "high", "height", "object height"),
                needs_words=True,
            ),
            var(
                "d_obj",
                "u",
                "meter",
                words=("in front", "from the", "away", "object is", "placed", "object distance"),
                needs_words=True,
            ),
            var("focal", "f", "meter", words=("focal",), needs_words=True),
        ),
        binding=Binding(
            asks=(
                "how tall is the image",
                "height of the image",
                "image height",
                "size of the image",
                "image size",
                "how big is the image",
                "how high is the image",
            ),
            result=("meter",),
            inputs=(frozenset({"d_obj", "focal", "h_obj"}),),
            cues=("converging lens", "convex lens", "concave mirror", "converging mirror"),
            excludes=("diverging", "convex mirror", "concave lens", "virtual", "signed"),
            negative_detail="inverted",
            requires=("d_obj - focal",),
        ),
    ),
    # A concave mirror given by its radius of curvature: f = R/2, then the
    # mirror equation. 40 cm and an object 30 cm away put the image 60 cm out.
    formula(
        "mirror_image_from_radius",
        "optics",
        "Mirror equation",
        "v",
        base_latex=r"\frac{1}{u} + \frac{1}{v} = \frac{2}{R}",
        assumptions=("a concave mirror, rays near the axis, the object outside F",),
        expression="1/(2/radius_curvature - 1/d_obj)",
        variables=(
            var(
                "radius_curvature",
                "R",
                "meter",
                words=("radius of curvature", "radius"),
                needs_words=True,
            ),
            var(
                "d_obj",
                "u",
                "meter",
                words=("object", "placed", "in front", "away", "from the mirror"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=(
                "where is the image",
                "where will the image",
                "where does the image",
                "image distance",
                "distance of the image",
                "image position",
                "position of the image",
                "location of the image",
                "how far from the mirror is the image",
            ),
            result=("meter",),
            inputs=(frozenset({"d_obj", "radius_curvature"}),),
            cues=("concave mirror", "converging mirror"),
            excludes=("convex", "diverging", "virtual", "lens", "signed"),
            nonnegative=True,
            # Inside F the image is virtual: behind the mirror, a sign the
            # conventions disagree on.
            requires=("2*d_obj - radius_curvature",),
        ),
    ),
    # Total internal reflection between two media: sin(theta_c) = n2 / n1,
    # from the denser medium. Glass into water is 62.5 degrees, not glass's
    # 41.8 degrees into air.
    formula(
        "critical_angle_between",
        "optics",
        "Critical angle",
        r"\theta_c",
        base_latex=r"\theta_c = \arcsin\frac{n_2}{n_1}",
        assumptions=("the light goes from the denser medium (n₁) into the less dense (n₂)",),
        expression="asin(n_rare/n_dense)*180/pi",
        variables=(
            var("n_dense", "n_1", dimensionless=True, words=("from", "leaves", "leaving")),
            var("n_rare", "n_2", dimensionless=True, words=("into", "to")),
        ),
        binding=Binding(
            asks=("critical angle",),
            result=("degree",),
            inputs=(frozenset({"n_dense", "n_rare"}),),
            nonnegative=True,
        ),
    ),
    # Light keeps its frequency in a medium and slows by n, so its wavelength
    # shrinks by n: 650 nm red light is 433 nm inside glass of n = 1.5.
    formula(
        "wavelength_in_medium",
        "optics",
        "Wavelength in a medium",
        r"\lambda_n",
        base_latex=r"\lambda_n = \frac{\lambda}{n}",
        assumptions=("the wavelength stated is the one in a vacuum (or air)",),
        expression="wavelength/n_index",
        variables=(
            var("wavelength", r"\lambda", "meter"),
            var(
                "n_index",
                "n",
                dimensionless=True,
                words=("refractive index", "index of refraction", "n =", "n="),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=(
                "wavelength in",
                "wavelength inside",
                "inside glass",
                "inside the glass",
                "inside water",
                "inside the water",
                "inside the medium",
                "in the glass",
                "in the water",
                "in the medium",
            ),
            result=("meter",),
            inputs=(frozenset({"n_index", "wavelength"}),),
            cues=("wavelength",),
            excludes=("frequency", "speed", "thickness", "film", "slit", "grating"),
            nonnegative=True,
        ),
    ),
    formula(
        "focal_from_power",
        "optics",
        "Lens power",
        "f",
        base_latex=r"f = \frac{1}{P}",
        expression="1/lens_power",
        variables=(var("lens_power", "P", "1 / meter"),),
        binding=Binding(
            asks=("focal length",),
            result=("meter",),
            inputs=(frozenset({"lens_power"}),),
            excludes=("diverging",),  # a concave lens's focal length is negative
            nonnegative=True,
        ),
    ),
)
