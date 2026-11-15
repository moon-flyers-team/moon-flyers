interface Props {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}

export function Field({ label, htmlFor, children }: Props) {
  return (
    <div className="sb-field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
    </div>
  );
}
