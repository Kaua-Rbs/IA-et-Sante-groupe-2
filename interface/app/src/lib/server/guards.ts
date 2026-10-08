import { error } from '@sveltejs/kit';
import type { SessionUser } from '#lib/types.ts';

type Capability = 'canPlan' | 'isClinical' | 'isStaff' | 'admin';

/** Refuse la page (403) si l'utilisateur n'a pas la capacité demandée. */
export function requireCapability(user: SessionUser | null, capability: Capability): SessionUser {
	if (!user) error(401, 'Non connecté');
	if (!user[capability]) error(403, "Votre rôle ne donne pas accès à cette page.");
	return user;
}
