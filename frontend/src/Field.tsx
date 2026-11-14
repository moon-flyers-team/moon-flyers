interface Props {
  label: string;
  children: React.ReactNode;
}

export function Field({ label, children }: Props) {
  return (
    <div className="sb-field">
      <label>{label}</label>
      {children}
    </div>
  );
}
