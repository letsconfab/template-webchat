import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Users } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { toast } from 'sonner';
import { api } from '../../services/api';

const inviteSchema = z.object({
  email: z.string().email('Invalid email address'),
  role: z.enum(['general', 'admin']).default('general'),
});

type InviteFormData = z.infer<typeof inviteSchema>;

interface InviteUserProps {
  selectedRole?: 'general' | 'admin';
}

export const InviteUser: React.FC<InviteUserProps> = ({ selectedRole = 'general' }) => {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
    setValue,
    watch,
  } = useForm<InviteFormData>({
    resolver: zodResolver(inviteSchema),
    defaultValues: {
      role: selectedRole,
    },
  });

  const currentRole = watch('role');

  const onSubmit = async (data: InviteFormData) => {
    try {
      const inviteData = {
        email: data.email,
        role: data.role === 'general' ? 'user' : 'admin'
      };
      await api.post('/admin/invite-user', inviteData);
      toast.success(`Invitation sent to ${data.email} as ${data.role}`);
      reset();
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to send invitation';
      toast.error(message);
    }
  };

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Invite User</CardTitle>
        <CardDescription>
          Send an invitation to a new user to join the platform
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Selected Role Display */}
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md">
          <div className="flex items-center">
            <Users className="h-5 w-5 text-blue-600 mr-2" />
            <div>
              <div className="text-sm font-medium text-blue-900">
                Role: {currentRole === 'admin' ? 'Admin' : 'General User'}
              </div>
              <div className="text-xs text-blue-700">
                {currentRole === 'admin' 
                  ? 'This user will have full system access' 
                  : 'This user will have standard access'}
              </div>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email Address</Label>
            <Input
              id="email"
              type="email"
              placeholder="Enter user's email"
              {...register('email')}
            />
            {errors.email && (
              <p className="text-sm text-red-500">{errors.email.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>Role Selection</Label>
            <div className="space-y-2">
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="radio"
                  value="general"
                  {...register('role')}
                  className="form-radio"
                />
                <span className="text-sm">General User</span>
              </label>
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="radio"
                  value="admin"
                  {...register('role')}
                  className="form-radio"
                />
                <span className="text-sm">Admin</span>
              </label>
            </div>
            {errors.role && (
              <p className="text-sm text-red-500">{errors.role.message}</p>
            )}
          </div>
          
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? 'Sending Invitation...' : 'Send Invitation'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
};
