import { useApp } from '../lib/context';
import { areaName, formatDate, money, seatingName } from '../lib/format';
import type { QueryCondition } from '../types/api';

export function AppliedConditions({ condition }: { condition: QueryCondition | null }) {
  const { locale, t } = useApp();
  function describe(node: QueryCondition): string {
    if ('all' in node) return node.all.map(describe).filter(Boolean).join(t(' · ', ' · '));
    if ('any' in node)
      return `(${node.any.map(describe).filter(Boolean).join(t(' 또는 ', ' or '))})`;
    if ('not' in node) return `${t('제외', 'Excluding')}: ${describe(node.not)}`;
    const labels: Record<string, string> = {
      starts_at: t('공연 시간', 'Show time'),
      area: t('지역', 'Area'),
      price_krw: t('가격', 'Price'),
      seating_type: t('관람 방식', 'Seating'),
      genre: t('장르', 'Genre'),
      lineup: t('출연진', 'Lineup'),
      title: t('공연명', 'Title'),
      description_ko: t('공연 소개', 'Description'),
    };
    const operators: Record<string, string> = {
      eq: '=',
      ne: '≠',
      lte: '≤',
      lt: '<',
      gte: '≥',
      gt: '>',
      contains: t('포함', 'contains'),
      in: t('중 하나', 'one of'),
    };
    let value = Array.isArray(node.value) ? node.value.join(', ') : String(node.value ?? '');
    if (node.field === 'starts_at') value = formatDate(value, locale);
    if (node.field === 'price_krw' && typeof node.value === 'number')
      value = money(node.value, locale);
    if (node.field === 'area' && ['sinchon', 'hongdae'].includes(value))
      value = areaName(value, locale);
    if (node.field === 'seating_type') value = seatingName(value, locale);
    return `${labels[node.field] || t('추가 조건', 'Additional condition')} ${operators[node.op] || ''} ${value}`;
  }
  if (!condition) return null;
  const description = describe(condition);
  return description ? (
    <p className="applied-conditions">
      <strong>{t('적용된 필수 조건', 'Applied requirements')}</strong>
      {description}
    </p>
  ) : null;
}
