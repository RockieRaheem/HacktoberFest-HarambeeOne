import { getPrimarySchool } from '@/lib/school';

export type AcademicPeriod = {
  id: string;
  academic_year_id: string;
  academic_year: number;
  academic_year_name: string;
  name: string;
  sequence: number;
  opening_date: string;
  closing_date: string;
  due_date: string;
  status: 'draft' | 'open' | 'closing' | 'closed';
  is_operational: boolean;
  activity_count: number;
};

let cachedPeriods: AcademicPeriod[] | null = null;
let pendingPeriods: Promise<AcademicPeriod[]> | null = null;

export async function getAcademicPeriods(): Promise<AcademicPeriod[]> {
  if (cachedPeriods) return cachedPeriods;
  if (!pendingPeriods) {
    pendingPeriods = getPrimarySchool()
      .then(school => fetch(`/api/backend/api/v1/academic-periods?school_id=${school.id}`, { cache: 'no-store' }))
      .then(async response => {
        if (!response.ok) throw new Error('Unable to load academic periods');
        cachedPeriods = await response.json() as AcademicPeriod[];
        return cachedPeriods;
      })
      .finally(() => { pendingPeriods = null; });
  }
  return pendingPeriods;
}

export async function getSelectedPeriod(): Promise<AcademicPeriod> {
  const [school, periods] = await Promise.all([getPrimarySchool(), getAcademicPeriods()]);
  if (!periods.length) throw new Error('No academic period has been configured');
  const stored = typeof window === 'undefined' ? null : localStorage.getItem(`harambee-period:${school.id}`);
  const selected = periods.find(period => period.id === stored)
    ?? periods.find(period => period.is_operational)
    ?? periods[0];
  if (typeof window !== 'undefined') localStorage.setItem(`harambee-period:${school.id}`, selected.id);
  return selected;
}

export async function selectPeriod(periodId: string): Promise<void> {
  const school = await getPrimarySchool();
  localStorage.setItem(`harambee-period:${school.id}`, periodId);
}

export function clearPeriods(): void {
  cachedPeriods = null;
  pendingPeriods = null;
}

export function periodQuery(period: AcademicPeriod): string {
  return `period_id=${encodeURIComponent(period.id)}`;
}
