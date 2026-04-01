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

