export type JsonSchema = Record<string, any>;

export function isSensitiveFieldName(name: string): boolean {
  const n = name.toLowerCase();
  return (
    n.includes('api_key') ||
    n.includes('apikey') ||
    n.includes('token') ||
    n.includes('password') ||
    n.includes('secret') ||
    n.endsWith('_key')
  );
}

export function buildUiSchemaFromSchema(schema: JsonSchema): Record<string, any> {
  // rjsf uiSchema shape loosely mirrors schema shape.
  const visit = (node: JsonSchema, path: string[]): Record<string, any> => {
    if (!node || typeof node !== 'object') return {};

    const out: Record<string, any> = {};

    const t = node.type;
    if (t === 'object' && node.properties && typeof node.properties === 'object') {
      for (const [k, v] of Object.entries(node.properties)) {
        out[k] = visit(v as JsonSchema, [...path, k]);
        if (isSensitiveFieldName(k)) {
          out[k] = { ...(out[k] || {}), 'ui:widget': 'password' };
        }
      }
    }

    if (node.additionalProperties && typeof node.additionalProperties === 'object') {
      // For dict-like objects, apply ui rules to the values too.
      out.additionalProperties = visit(node.additionalProperties as JsonSchema, [
        ...path,
        '(additionalProperties)',
      ]);
    }

    if (t === 'array' && node.items && typeof node.items === 'object') {
      out.items = visit(node.items as JsonSchema, [...path, '(items)']);
    }

    return out;
  };

  return visit(schema, []);
}

export function buildGroupSchema(
  fullFilteredSchema: JsonSchema,
  groupKey: string,
): JsonSchema | null {
  if (!fullFilteredSchema || typeof fullFilteredSchema !== 'object') return null;
  const properties = fullFilteredSchema.properties;
  if (!properties || typeof properties !== 'object') return null;
  const groupSchema = properties[groupKey];
  if (!groupSchema || typeof groupSchema !== 'object') return null;

  const defs = fullFilteredSchema.$defs;
  if (defs && typeof defs === 'object') {
    return { ...(groupSchema as JsonSchema), $defs: defs };
  }

  return groupSchema as JsonSchema;
}

/** Top-level nested settings groups (e.g. content, filesystem) are plain objects; everything else is edited under General. */
export function isTopLevelObjectGroup(value: unknown): boolean {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function buildGeneralSchema(
  fullFilteredSchema: JsonSchema | null,
  generalKeys: string[],
): JsonSchema | null {
  if (!fullFilteredSchema || typeof fullFilteredSchema !== 'object') return null;
  const properties = fullFilteredSchema.properties;
  if (!properties || typeof properties !== 'object') return null;
  const props = properties as Record<string, JsonSchema>;
  const picked: Record<string, JsonSchema> = {};
  for (const k of generalKeys) {
    if (props[k]) picked[k] = props[k];
  }
  if (!Object.keys(picked).length) return null;

  const reqFull = fullFilteredSchema.required;
  const required = Array.isArray(reqFull)
    ? reqFull.filter((r: string) => generalKeys.includes(r))
    : [];

  const defs = fullFilteredSchema.$defs;
  const out: JsonSchema = {
    type: 'object',
    title: 'General',
    properties: picked,
    required,
  };
  if (defs && typeof defs === 'object') {
    out.$defs = defs;
  }
  return out;
}

export function isSchemaLikelyNestedObject(propSchema: JsonSchema | undefined): boolean {
  if (!propSchema || typeof propSchema !== 'object') return false;
  if (typeof propSchema.$ref === 'string') return true;
  const t = propSchema.type;
  if (t === 'object' && propSchema.properties && Object.keys(propSchema.properties).length > 0) {
    return true;
  }
  if (Array.isArray(t) && t.includes('object')) {
    if (propSchema.properties && Object.keys(propSchema.properties).length > 0) return true;
  }
  const anyOf = propSchema.anyOf;
  if (Array.isArray(anyOf)) {
    return anyOf.some(
      (b) =>
        b &&
        typeof b === 'object' &&
        (typeof (b as JsonSchema).$ref === 'string' ||
          (b as JsonSchema).type === 'object'),
    );
  }
  const oneOf = propSchema.oneOf;
  if (Array.isArray(oneOf)) {
    return oneOf.some(
      (b) =>
        b &&
        typeof b === 'object' &&
        (typeof (b as JsonSchema).$ref === 'string' ||
          (b as JsonSchema).type === 'object'),
    );
  }
  return false;
}

/** Direct child keys of a top-level settings object that are nested plain objects (own sidebar row). */
export function nestedObjectChildKeys(
  groupFullSchema: JsonSchema | null,
  groupData: Record<string, unknown> | undefined,
): string[] {
  const keys = new Set<string>();
  if (groupData && typeof groupData === 'object' && !Array.isArray(groupData)) {
    for (const [k, v] of Object.entries(groupData)) {
      if (isTopLevelObjectGroup(v)) keys.add(k);
    }
  }
  const props = groupFullSchema?.properties;
  if (props && typeof props === 'object') {
    for (const [k, sub] of Object.entries(props as Record<string, JsonSchema>)) {
      if (keys.has(k)) continue;
      const val = groupData?.[k];
      if (val === undefined && isSchemaLikelyNestedObject(sub)) keys.add(k);
    }
  }
  return [...keys].sort();
}

/** Schema for editing only non-object fields on a top-level group (e.g. notifications.enabled). */
export function buildScalarSubsetGroupSchema(
  groupFullSchema: JsonSchema | null,
  groupData: Record<string, unknown> | undefined,
): JsonSchema | null {
  if (!groupFullSchema?.properties || typeof groupFullSchema.properties !== 'object') return null;
  const props = groupFullSchema.properties as Record<string, JsonSchema>;
  const picked: Record<string, JsonSchema> = {};
  const required: string[] = [];
  const reqFull = groupFullSchema.required;

  for (const [k, sub] of Object.entries(props)) {
    const val = groupData?.[k];
    if (isTopLevelObjectGroup(val)) continue;
    if (val === undefined && isSchemaLikelyNestedObject(sub)) continue;
    picked[k] = sub;
  }
  if (!Object.keys(picked).length) return null;

  if (Array.isArray(reqFull)) {
    for (const r of reqFull) {
      if (r in picked) required.push(r);
    }
  }

  const out: JsonSchema = {
    type: 'object',
    title: groupFullSchema.title,
    properties: picked,
    required,
  };
  const defs = groupFullSchema.$defs;
  if (defs && typeof defs === 'object') out.$defs = defs;
  return out;
}

export function buildNestedPropertySchema(
  fullFilteredSchema: JsonSchema,
  topKey: string,
  nestedKey: string,
): JsonSchema | null {
  const group = buildGroupSchema(fullFilteredSchema, topKey);
  if (!group?.properties || typeof group.properties !== 'object') return null;
  const sub = (group.properties as Record<string, JsonSchema>)[nestedKey];
  if (!sub || typeof sub !== 'object') return null;
  const defs = group.$defs ?? fullFilteredSchema.$defs;
  if (defs && typeof defs === 'object') {
    return { ...(sub as JsonSchema), $defs: defs };
  }
  return sub as JsonSchema;
}

