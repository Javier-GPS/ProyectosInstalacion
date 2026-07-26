/** Canonical FE → API mapping for shared calculation/report fields. */

type ConfigLike = Record<string, any>;

const value = (config: ConfigLike, override: ConfigLike | undefined, key: string, ...aliases: string[]) => {
  for (const source of [override, config]) {
    if (!source) continue;
    for (const candidate of [key, ...aliases]) {
      if (source[candidate] !== undefined && source[candidate] !== null) return source[candidate];
    }
  }
  return undefined;
};

export const buildCanonicalConfigRequest = (config: ConfigLike, override?: ConfigLike) => {
  const targetFlux = value(config, override, 'target_flux');
  const numericTargetFlux = Number(targetFlux);
  const armLength = value(config, override, 'arm_length', 'armLength');
  const tilt = value(config, override, 'tilt', 'armTiltAngle');

  return {
    road_width: value(config, override, 'road_width'),
    sidewalk_left: value(config, override, 'sidewalk_left'),
    sidewalk_right: value(config, override, 'sidewalk_right'),
    lanes: value(config, override, 'lanes'),
    median_width: value(config, override, 'median_width'),
    arrangement: value(config, override, 'arrangement'),
    height: value(config, override, 'height'),
    spacing: value(config, override, 'spacing'),
    arm_length: armLength,
    armLength,
    pole_offset: value(config, override, 'pole_offset'),
    pole_side: value(config, override, 'pole_side'),
    tilt,
    armTiltAngle: tilt,
    optic_family: value(config, override, 'optic_family'),
    power: value(config, override, 'power'),
    target_flux: Number.isFinite(numericTargetFlux) && numericTargetFlux > 0 ? numericTargetFlux : null,
    ldt_id: value(config, override, 'ldt_id'),
    manufacturer: value(config, override, 'manufacturer'),
    model_family: value(config, override, 'model_family'),
    gama: value(config, override, 'gama'),
    difusor: value(config, override, 'difusor'),
    lente: value(config, override, 'lente'),
    led_type: value(config, override, 'led_type'),
    lighting_class: value(config, override, 'lighting_class'),
    mf: value(config, override, 'mf'),
    pavement: value(config, override, 'pavement'),
    cct: value(config, override, 'cct'),
    cri: value(config, override, 'cri'),
    language: value(config, override, 'language'),
  };
};
