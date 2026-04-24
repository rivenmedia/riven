import { Component, type ReactNode, useEffect, useMemo, useState } from 'react';
import Form from '@rjsf/core';
import validator from '@rjsf/validator-ajv8';
import type { RJSFSchema, UiSchema } from '@rjsf/utils';

import {
  buildUiSchemaFromSchema,
  type JsonSchema,
} from '../schema/settingsSchema';

function RjsfTextButton({
  children,
  onClick,
  className,
  title,
  type = 'button',
  disabled,
}: {
  children: ReactNode;
  onClick?: (e: any) => void;
  className?: string;
  title?: string;
  type?: 'button' | 'submit';
  disabled?: boolean;
}) {
  return (
    <button
      type={type}
      className={className || 'btn btn--secondary btn--small'}
      title={title}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

class FormErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { hasError: boolean }
> {
  state: { hasError: boolean } = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}

export function SettingsGroupForm({
  groupKey,
  groupLabel,
  value,
  schema,
  onSave,
  jsonFallback,
  noSchemaSlot,
}: {
  groupKey: string;
  groupLabel?: string;
  value: unknown;
  schema: JsonSchema | null;
  onSave: (value: unknown) => Promise<void> | void;
  jsonFallback: React.ReactNode;
  /** When there is no JSON schema, show this instead of the raw JSON editor (e.g. empty parent panel). */
  noSchemaSlot?: React.ReactNode;
}) {
  const [formData, setFormData] = useState<any>(value ?? null);

  useEffect(() => {
    setFormData(value ?? null);
  }, [value]);

  const saveLabel = groupLabel ?? groupKey;

  const rjsfSchema = useMemo(() => schema as unknown as RJSFSchema, [schema]);
  const uiSchema = useMemo(() => {
    if (!schema) return {} as UiSchema;
    return buildUiSchemaFromSchema(schema) as UiSchema;
  }, [schema]);

  if (!schema) {
    if (noSchemaSlot) return <>{noSchemaSlot}</>;
    return <>{jsonFallback}</>;
  }

  return (
    <FormErrorBoundary fallback={jsonFallback}>
      <div className="settings-form">
        <Form
          schema={rjsfSchema}
          uiSchema={uiSchema}
          validator={validator}
          formData={formData}
          onChange={(e) => setFormData(e.formData)}
          onSubmit={async () => {
            await onSave(formData);
          }}
          templates={{
            ButtonTemplates: {
              AddButton: (props: any) => (
                <RjsfTextButton
                  className="btn btn--secondary btn--small"
                  title={props.title || 'Add'}
                  onClick={props.onClick}
                  disabled={props.disabled}
                >
                  Add
                </RjsfTextButton>
              ),
              RemoveButton: (props: any) => (
                <RjsfTextButton
                  className="btn btn--secondary btn--small"
                  title={props.title || 'Remove'}
                  onClick={props.onClick}
                  disabled={props.disabled}
                >
                  Remove
                </RjsfTextButton>
              ),
              MoveUpButton: (props: any) => (
                <RjsfTextButton
                  className="btn btn--secondary btn--small"
                  title={props.title || 'Move up'}
                  onClick={props.onClick}
                  disabled={props.disabled}
                >
                  Up
                </RjsfTextButton>
              ),
              MoveDownButton: (props: any) => (
                <RjsfTextButton
                  className="btn btn--secondary btn--small"
                  title={props.title || 'Move down'}
                  onClick={props.onClick}
                  disabled={props.disabled}
                >
                  Down
                </RjsfTextButton>
              ),
              CopyButton: (props: any) => (
                <RjsfTextButton
                  className="btn btn--secondary btn--small"
                  title={props.title || 'Copy'}
                  onClick={props.onClick}
                  disabled={props.disabled}
                >
                  Copy
                </RjsfTextButton>
              ),
            },
          }}
          liveValidate
          noHtml5Validate
        >
          <div className="toolbar">
            <button type="submit" className="btn btn--primary btn--small">
              Save {saveLabel}
            </button>
          </div>
        </Form>
      </div>
    </FormErrorBoundary>
  );
}

