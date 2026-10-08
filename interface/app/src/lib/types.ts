// Types des réponses de l'API KYST (voir interface/docs/BDD.md) et libellés d'affichage.

export type Role = 'user' | 'doctor' | 'admin' | 'secretary' | 'planner';
export type CareType = 'ambulatory' | 'conventional';
export type RequestStatus = 'pending' | 'scheduled' | 'done' | 'cancelled';
export type ProposalStatus = 'proposed' | 'accepted' | 'rejected' | 'superseded';
export type CaseStatus = 'planned' | 'done' | 'cancelled';

/** Utilisateur de la session, tiré du jeton d'accès. */
export interface SessionUser {
	username: string;
	fullName: string;
	displayName: string;
	admin: boolean;
	doctor: boolean;
	roles: Role[];
	/** Cadre de bloc / gestion des lits, ou admin */
	canPlan: boolean;
	/** Chirurgien ou secrétariat, ou admin */
	isClinical: boolean;
	/** Accès aux patients et au planning détaillé */
	isStaff: boolean;
}

export interface Group {
	id: number;
	name: Role;
}

export interface User {
	id: string;
	username: string;
	email: string;
	full_name: string;
	disabled: boolean;
	validated: boolean;
	groups: Group[];
}

export interface Specialty {
	id: number;
	name: string;
}

export interface Room {
	id: number;
	name: string;
	default_specialty_id: number | null;
	active: boolean;
}

export interface BedUnit {
	id: number;
	name: string;
	care_type: CareType;
	capacity: number;
	active: boolean;
}

export interface Surgeon {
	id: number;
	name: string;
	specialty_id: number;
	user_id: string | null;
}

export interface Vacation {
	id: number;
	room_id: number;
	specialty_id: number;
	surgeon_id: number | null;
	date: string;
	start_time: string;
	duration_min: number;
}

export interface Patient {
	id: string;
	external_ref: string | null;
	birth_year: number;
	sex: 1 | 2;
	created_at: string;
}

export interface SurgicalRequest {
	id: string;
	patient_id: string;
	surgeon_id: number;
	specialty_id: number;
	principal_diagnosis: string;
	ccam_codes: string[];
	intervention_type: string | null;
	earliest_date: string;
	latest_date: string | null;
	status: RequestStatus;
	created_by: string;
	created_at: string;
}

export interface Prediction {
	id: string;
	request_id: string;
	room_minutes: number;
	room_minutes_low: number | null;
	room_minutes_high: number | null;
	los_days: number;
	los_days_low: number | null;
	los_days_high: number | null;
	care_type: CareType;
	model_version: string;
	source: string;
	created_at: string;
}

export interface Proposal {
	id: string;
	request_id: string;
	prediction_id: string;
	rank: number;
	vacation_id: number;
	bed_unit_id: number;
	admission_date: string;
	discharge_date: string;
	planned_minutes: number;
	score: number;
	reasons: string[];
	scheduler: string;
	status: ProposalStatus;
	created_at: string;
	decided_by: string | null;
	decided_at: string | null;
}

export interface PlannedCase {
	id: string;
	request_id: string;
	proposal_id: string;
	vacation_id: number;
	bed_unit_id: number;
	admission_date: string;
	discharge_date: string;
	planned_minutes: number;
	status: CaseStatus;
	actual_room_minutes: number | null;
	actual_los_days: number | null;
	created_at: string;
}

export interface UnitOccupancy {
	bed_unit_id: number;
	name: string;
	care_type: CareType;
	capacity: number;
	days: { date: string; occupied: number; rate: number }[];
}

export interface VacationFill {
	vacation_id: number;
	date: string;
	room_id: number;
	room_name: string;
	specialty_id: number;
	duration_min: number;
	planned_minutes: number;
	fill_rate: number;
}

export interface PredictionAccuracy {
	evaluated_cases: number;
	room_minutes_mae: number | null;
	room_minutes_overestimated: number;
	room_minutes_underestimated: number;
	los_days_mae: number | null;
}

export interface Health {
	status: string;
	name: string;
	version: string;
	ai_backend: string;
	emergency_margin: number;
	proposal_count: number;
}

// --- Libellés ---

export const ROLE_LABELS: Record<Role, string> = {
	user: 'Lecture',
	doctor: 'Chirurgien',
	secretary: 'Secrétariat',
	planner: 'Cadre bloc / lits',
	admin: 'Administrateur'
};

export const CARE_TYPE_LABELS: Record<CareType, string> = {
	ambulatory: 'Ambulatoire',
	conventional: 'Hospitalisation conventionnelle'
};

export const REQUEST_STATUS_LABELS: Record<RequestStatus, string> = {
	pending: 'À programmer',
	scheduled: 'Programmée',
	done: 'Réalisée',
	cancelled: 'Annulée'
};

export const PROPOSAL_STATUS_LABELS: Record<ProposalStatus, string> = {
	proposed: 'Proposée',
	accepted: 'Acceptée',
	rejected: 'Écartée',
	superseded: 'Remplacée'
};

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
	planned: 'Programmée',
	done: 'Réalisée',
	cancelled: 'Annulée'
};
