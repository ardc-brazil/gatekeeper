-- Triggers for enable Casbin Watcher component
-- Even after creates trigger, is not working 100%, needs investigation

CREATE OR REPLACE FUNCTION public.casbin_rule_notify_trigger() RETURNS trigger AS $$
DECLARE
    BEGIN
        IF (TG_OP = 'DELETE') THEN

			OLD.v1 = '';
			OLD.v2 = '';
			OLD.v3 = '';
			OLD.v4 = '';
			OLD.v5 = '';
			
			PERFORM pg_notify(CAST('casbin_role_watcher' as TEXT), row_to_json(OLD)::text);
		ELSE 
	        PERFORM pg_notify(CAST('casbin_role_watcher' as TEXT), row_to_json(NEW)::text);
		END IF;
		
        RETURN new;
    END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE  TRIGGER casbing_police_updated_trigger AFTER UPDATE ON public.casbin_rule
FOR EACH ROW EXECUTE PROCEDURE public.casbin_rule_notify_trigger();

CREATE OR REPLACE TRIGGER casbing_police_insert_trigger AFTER INSERT ON public.casbin_rule
FOR EACH ROW EXECUTE PROCEDURE public.casbin_rule_notify_trigger();

CREATE OR REPLACE TRIGGER casbing_police_delete_trigger AFTER DELETE ON public.casbin_rule
FOR EACH ROW EXECUTE PROCEDURE public.casbin_rule_notify_trigger();