export type School = { id: string; name: string; district?: string | null; emis_code?: string | null; role?: 'owner'|'bursar'|'cashier'|'auditor'; permissions?: string[]; programmes?: { programme_code: string; display_name: string; sort_order: number }[] };
let cachedSchool: School | null = null;
let pendingSchool: Promise<School> | null = null;

export function getPrimarySchool(): Promise<School> {
  if (cachedSchool) return Promise.resolve(cachedSchool);
  if (!pendingSchool) {
    pendingSchool = fetch('/api/current-school', {cache:'no-store'})
      .then(async response => {
        if (!response.ok) throw new Error('Unable to load institution');
        cachedSchool = await response.json() as School;
        return cachedSchool;
      })
      .finally(() => { pendingSchool = null; });
  }
  return pendingSchool;
}

export function setPrimarySchool(school: School): void {
  cachedSchool = school;
}

export function clearPrimarySchool(): void {
  cachedSchool = null;
  pendingSchool = null;
}
